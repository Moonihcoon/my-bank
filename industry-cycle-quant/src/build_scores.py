"""산업 사이클 + 종목 점수 계산 → docs/data/dashboard.json

입력(CSV, data/ 아래. 지표·재무는 as_of 가 다른 행을 여러 개 쌓아도 된다 — 시점별로 '그때 알 수 있던 값'만 쓴다):
  industry_map.csv      code,name,market,industry
  industry_signals.csv  industry,as_of,phase,inventory,price,orders,supply   (신호 -1~+1, 빈칸=미확인)
  fundamentals.csv      code,as_of,avail,op_margin_chg,est_revision,fcf_positive,per_norm_pct,debt_ratio
  prices/{code}.csv     date,open,high,low,close,volume,value
  benchmark.csv         date,close
배점(초안, 백테스트 후 확정): 산업 35 / 실적 25 / 추세 20 / 밸류 10 / 위험 10
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
W = {"industry": 35, "earnings": 25, "trend": 20, "valuation": 10, "risk": 10}
PHASE_SCORE = {"하락": 0.10, "전환": 0.70, "횡보": 0.45, "상승": 0.80, "과열": 0.40}
STALE_DAYS = {"industry": 120}
FUND_LAG_DAYS = 60  # avail 열이 없을 때 as_of 이후 이 기간이 지나야 사용 (공시 지연 가정; 연간은 90일 권장)
MIN_TURNOVER = 1e9  # 일평균 거래대금 10억원 미만이면 유동성 필터 탈락 (초안)


def band(score: float) -> str:
    if score >= 80:
        return "우선 검토 후보"
    if score >= 70:
        return "매수 후보 관찰"
    if score >= 55:
        return "관찰"
    return "제외 또는 보류"


def _nn(v) -> bool:
    return v is not None and not pd.isna(v)


def age_days(as_of, today: date):
    if not _nn(as_of) or as_of == "":
        return None
    return (today - pd.to_datetime(as_of).date()).days


def industry_score(row, today):
    if row is None:
        return 0.5, 0.0, ["산업 지표 미확인"]
    parts, notes = [], []
    phase = row.get("phase")
    if isinstance(phase, str) and phase in PHASE_SCORE:
        parts.append(PHASE_SCORE[phase])
        notes.append(f"국면 {phase}")
    for k, label in [("inventory", "재고"), ("price", "가격"), ("orders", "수주"), ("supply", "공급")]:
        v = row.get(k)
        if _nn(v):
            parts.append((float(v) + 1) / 2)
            notes.append(f"{label} {float(v):+.1f}")
    conf = len(parts) / 5
    a = age_days(row.get("as_of"), today)
    if a is not None and a > STALE_DAYS["industry"]:
        conf *= 0.5
        notes.append(f"지표 {a}일 경과(지연)")
    return (float(np.mean(parts)) if parts else 0.5), conf, notes


def earnings_score(row):
    if row is None:
        return 0.5, 0.0, ["재무 미확인"]
    s, notes = [], []
    v = row.get("op_margin_chg")
    if _nn(v):
        s.append(float(np.clip((v + 5) / 10, 0, 1)))
        notes.append(f"영업이익률 {v:+.1f}%p")
    v = row.get("est_revision")
    if _nn(v):
        s.append(float(np.clip((v + 10) / 20, 0, 1)))
        notes.append(f"추정치 {v:+.1f}%")
    v = row.get("fcf_positive")
    if _nn(v):
        s.append(1.0 if int(v) else 0.2)
        notes.append("FCF " + ("흑자" if int(v) else "적자"))
    return (float(np.mean(s)) if s else 0.5), len(s) / 3, notes


def trend_metrics(px: pd.DataFrame, bench):
    c = px["close"].astype(float)
    if len(c) < 130:
        return None
    r6 = c.iloc[-1] / c.iloc[-127] - 1
    r12 = c.iloc[-1] / c.iloc[-253] - 1 if len(c) >= 253 else np.nan
    ma200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    rel6 = r6
    if bench is not None and len(bench) >= 127:
        b = bench["close"].astype(float)
        rel6 = r6 - (b.iloc[-1] / b.iloc[-127] - 1)
    vol = c.pct_change().tail(60).std() * np.sqrt(252)
    turn = px["value"].astype(float).tail(60).mean()
    return dict(r6=r6, r12=r12, rel6=rel6, above_ma200=bool(c.iloc[-1] > ma200) if pd.notna(ma200) else None,
                vol=float(vol), turnover=float(turn), last=px["date"].iloc[-1], close=float(c.iloc[-1]))


# ---------- 데이터 로딩 / 시점 선택 ----------
def load_data(d: Path) -> dict:
    def rd(name, **kw):
        p = d / name
        return pd.read_csv(p, **kw) if p.exists() and p.stat().st_size > 0 else pd.DataFrame()
    data = {"imap": pd.read_csv(d / "industry_map.csv", dtype={"code": str}),
            "sig": rd("industry_signals.csv"), "fun": rd("fundamentals.csv", dtype={"code": str}),
            "bench": rd("benchmark.csv"), "prices": {}}
    for df in (data["sig"], data["fun"]):
        if len(df) and "as_of" in df:
            df["as_of"] = pd.to_datetime(df["as_of"])
    if len(data["fun"]):
        f = data["fun"]
        if "avail" not in f:
            f["avail"] = f["as_of"] + timedelta(days=FUND_LAG_DAYS)
        f["avail"] = pd.to_datetime(f["avail"])
        if "debt_ratio" not in f and "net_debt_ratio" in f:
            f["debt_ratio"] = f["net_debt_ratio"]
    if len(data["bench"]):
        data["bench"]["date"] = pd.to_datetime(data["bench"]["date"])
    for code in data["imap"]["code"]:
        p = d / "prices" / f"{code}.csv"
        if p.exists():
            px = pd.read_csv(p)
            px["date"] = pd.to_datetime(px["date"])
            data["prices"][code] = px.sort_values("date").reset_index(drop=True)
    return data


def latest_rows(df: pd.DataFrame, key: str, asof: pd.Timestamp, date_col: str) -> dict:
    if not len(df):
        return {}
    cur = df[df[date_col] <= asof]
    if not len(cur):
        return {}
    cur = cur.sort_values(date_col).groupby(key).tail(1)
    return {r[key]: r for r in cur.to_dict("records")}


def score_at(data: dict, asof_d: date) -> dict:
    """asof_d 시점에 알 수 있던 자료만으로 점수를 계산한다 (백테스트와 실사용 공통)."""
    asof = pd.Timestamp(asof_d)
    imap = data["imap"]
    sig_by = latest_rows(data["sig"], "industry", asof, "as_of")
    fun_by = latest_rows(data["fun"], "code", asof, "avail")
    bench = data["bench"][data["bench"]["date"] <= asof] if len(data["bench"]) else None

    inds = {}
    for name in imap["industry"].unique():
        sc, conf, notes = industry_score(sig_by.get(name), asof_d)
        row = sig_by.get(name, {})
        ph = row.get("phase")
        inds[name] = {"industry": name, "score": round(sc * W["industry"], 1), "max": W["industry"],
                      "confidence": round(conf, 2), "phase": ph if isinstance(ph, str) else "미확인",
                      "as_of": str(pd.Timestamp(row["as_of"]).date()) if "as_of" in row else None, "notes": notes}
    stocks, problems = [], []
    for r in imap.to_dict("records"):
        px = data["prices"].get(r["code"])
        if px is None:
            problems.append({"code": r["code"], "issue": "시세 파일 없음"})
            continue
        px = px[px["date"] <= asof]
        m = trend_metrics(px, bench)
        if m is None:
            problems.append({"code": r["code"], "issue": "시세 이력 부족(<130일)"})
            continue
        ind = inds[r["industry"]]
        f = fun_by.get(r["code"])
        es, econf, enotes = earnings_score(f)
        trend = float(np.clip((m["rel6"] + 0.2) / 0.5, 0, 1)) * 0.6 + (0.4 if m["above_ma200"] else 0.0)
        val = 0.5
        if f and _nn(f.get("per_norm_pct")):
            val = float(1 - np.clip(f["per_norm_pct"] / 100, 0, 1))
        risk = 0.5
        if f and _nn(f.get("debt_ratio")):
            risk = float(1 - np.clip(f["debt_ratio"] / 300, 0, 1))  # 부채비율(부채/자본, %) 300% 이상이면 0
        risk = risk * 0.7 + float(1 - np.clip((m["vol"] - 0.2) / 0.6, 0, 1)) * 0.3
        parts = {"industry": ind["score"], "earnings": round(es * W["earnings"], 1),
                 "trend": round(trend * W["trend"], 1), "valuation": round(val * W["valuation"], 1),
                 "risk": round(risk * W["risk"], 1)}
        total = round(sum(parts.values()), 1)
        filt = {"추세": bool(m["above_ma200"]), "유동성": m["turnover"] >= MIN_TURNOVER,
                "위험": risk >= 0.3, "자료": ind["confidence"] >= 0.4 and econf >= 0.34}
        label = band(total)
        if label == "우선 검토 후보" and not all(filt.values()):
            label = "매수 후보 관찰"
        last = pd.Timestamp(m["last"]).date()
        stocks.append({
            "code": r["code"], "name": r["name"], "market": r["market"], "industry": r["industry"],
            "total": total, "label": label, "parts": parts, "filters": filt,
            "ret6": round(m["r6"] * 100, 1), "rel6": round(m["rel6"] * 100, 1),
            "vol": round(m["vol"] * 100, 1), "turnover_eok": round(m["turnover"] / 1e8, 1),
            "last_price_date": str(last), "price_stale_days": (asof_d - last).days,
            "notes": enotes + ind["notes"][:3],
            "spark": [round(float(x), 2) for x in px["close"].tail(120).iloc[::4]],
        })
    stocks.sort(key=lambda s: -s["total"])
    return {"industries": sorted(inds.values(), key=lambda x: -x["score"]), "stocks": stocks,
            "problems": problems, "n_map": len(imap)}


def run(d: Path, today: date, demo: bool, max_stocks: int = 500) -> dict:
    res = score_at(load_data(d), today)
    n_scored = len(res["stocks"])
    res["stocks"] = res["stocks"][:max_stocks]  # 화면용 상위 N개만 저장
    return {
        "is_demo": demo, "generated_at": datetime.now().isoformat(timespec="minutes"), "as_of": str(today),
        "weights": W, "industries": res["industries"], "stocks": res["stocks"],
        "data_quality": {"problems": res["problems"][:200], "n_problems": len(res["problems"]), "n_stocks": n_scored, "n_shown": len(res["stocks"]), "n_map": res["n_map"]},
        "disclaimer": "투자 의사결정 보조 도구이며 주문을 자동 실행하지 않습니다. 점수 구간은 백테스트 확정 전 초안입니다.",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "data"), help="데이터 폴더")
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "dashboard.json"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--today", default=str(date.today()))
    ap.add_argument("--max-stocks", type=int, default=500)
    a = ap.parse_args()
    res = run(Path(a.root), date.fromisoformat(a.today), a.demo, a.max_stocks)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out} 저장: 종목 {res['data_quality']['n_stocks']}/{res['data_quality']['n_map']}")
