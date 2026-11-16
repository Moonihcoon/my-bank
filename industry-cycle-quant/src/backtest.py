"""워크포워드 방식 백테스트 → docs/data/backtest.json

원칙
- 신호는 각 월말 종가 기준으로 '그때 알 수 있던 자료'만 써서 계산(score_at, as_of≤시점, 재무는 avail≤시점).
- 매매는 신호 다음 거래일 종가에 체결 (미래참조 방지).
- 신호는 월간 평가하되 리밸런싱은 --rebalance 개월(기본 3=분기)마다.
- 상장폐지 종목: data/prices 에 상폐 종목 파일(마지막 거래일까지)이 있어야 생존편향이 줄어든다.
  시세가 중간에 끊긴 종목은 마지막 종가에 --delist-haircut 만큼 손실을 더해 청산한다(기본 0 → 낙관적, 보수적으로는 0.5 등).
- 비용 기본값은 '가정'이다. 실제 수수료·증권거래세율·슬리피지는 확인 후 인자로 넣을 것.
- 가중치·구간 최적화는 하지 않는다. --split 이전은 표본 내(참고), 이후는 표본 외 성과로 따로 보고한다.
  점수 기준을 바꿀 때는 표본 내에서만 조정하고 표본 외는 한 번만 본다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_scores as bs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def month_ends(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return list(s.groupby([dates.year, dates.month]).max())


def metrics(v: pd.Series) -> dict:
    v = v.dropna()
    if len(v) < 3:
        return {}
    r = v.pct_change().dropna()
    yrs = (v.index[-1] - v.index[0]).days / 365.25
    dd = (v / v.cummax() - 1).min()
    return {"CAGR": f"{((v.iloc[-1] / v.iloc[0]) ** (1 / yrs) - 1) * 100:.1f}%" if yrs > 0 else "-",
            "MDD": f"{dd * 100:.1f}%",
            "Sharpe": f"{r.mean() / r.std() * np.sqrt(252):.2f}" if r.std() > 0 else "-",
            "누적수익": f"{(v.iloc[-1] / v.iloc[0] - 1) * 100:.1f}%"}


def run(a) -> dict:
    data = bs.load_data(Path(a.root))
    close = pd.DataFrame({c: p.set_index("date")["close"] for c, p in data["prices"].items()}).sort_index()
    idx = close.index
    bench = data["bench"].set_index("date")["close"].reindex(idx).ffill() if len(data["bench"]) else None
    mends = [m for m in month_ends(idx) if (idx <= m).sum() >= 130]
    rebal = mends[:: a.rebalance]
    cost_in = a.commission + a.slippage
    cost_out = a.commission + a.slippage + a.sell_tax

    value, hold, curve = 1.0, {}, []
    daily = pd.Series(dtype=float)
    turnover_sum, n_hold = 0.0, []
    for k, m in enumerate(rebal):
        sc = bs.score_at(data, m.date())
        picks = [s for s in sc["stocks"] if s["total"] >= a.min_score and all(s["filters"].values())]
        picks = picks[: a.top_n]
        nxt = idx[idx > m]
        if not len(nxt):
            break
        entry = nxt[0]
        end = rebal[k + 1] if k + 1 < len(rebal) else idx[-1]
        # 신규 편입/청산 비용 (단순화: 비중 변화분 × 비용)
        new = {s["code"]: 1 / len(picks) for s in picks} if picks else {}
        codes = set(new) | set(hold)
        buy = sum(max(new.get(c, 0) - hold.get(c, 0), 0) for c in codes)
        sell = sum(max(hold.get(c, 0) - new.get(c, 0), 0) for c in codes)
        value *= 1 - buy * cost_in - sell * cost_out
        turnover_sum += (buy + sell) / 2
        hold = new
        n_hold.append(len(hold))
        seg = idx[(idx >= entry) & (idx <= end)]
        if not len(seg):
            continue
        if hold:
            sub = close.loc[seg, list(hold)].copy()
            # 시세가 끊긴 종목: 마지막 값 유지 후 마지막 날 손실 반영
            last_valid = sub.apply(lambda s: s.last_valid_index())
            for c in hold:
                if last_valid[c] is not None and last_valid[c] < seg[-1]:
                    sub.loc[last_valid[c]:, c] = sub[c].loc[last_valid[c]] * (1 - a.delist_haircut)
            rel = sub.ffill().div(sub.ffill().bfill().iloc[0])
            w = pd.Series(hold)
            path = (rel * w).sum(axis=1) + (1 - w.sum())
        else:
            path = pd.Series(1.0, index=seg)
        s = path * value
        daily = pd.concat([daily, s[~s.index.isin(daily.index)]])
        value = float(s.iloc[-1])
        # 다음 구간 비중은 수익 후 비중으로 drift 하지만 단순화를 위해 동일가중 재설정 가정
    daily = daily.sort_index()
    bser = (bench.reindex(daily.index).ffill() / bench.reindex(daily.index).ffill().iloc[0]) if bench is not None and len(daily) else None
    split = pd.Timestamp(a.split) if a.split else None
    out = {"summary": {}, "note": "", "curve": [], "periods": {}}
    full = metrics(daily)
    out["summary"] = {**{f"전략 {k}": v for k, v in full.items()}}
    if bser is not None:
        for k, v in metrics(bser).items():
            out["summary"][f"기준지수 {k}"] = v
    yrs = max((daily.index[-1] - daily.index[0]).days / 365.25, 1e-9) if len(daily) else 1
    out["summary"]["연 회전율"] = f"{turnover_sum / yrs * 100:.0f}%"
    out["summary"]["평균 보유 종목수"] = f"{np.mean(n_hold):.1f}" if n_hold else "0"
    if split is not None and len(daily):
        for nm, part, bpart in (("표본 내(참고)", daily[daily.index < split], bser[bser.index < split] if bser is not None else None),
                                ("표본 외(검증)", daily[daily.index >= split], bser[bser.index >= split] if bser is not None else None)):
            out["periods"][nm] = {"전략": metrics(part), "기준지수": metrics(bpart) if bpart is not None else {}}
    mo = daily.groupby([daily.index.year, daily.index.month]).last()
    ds = daily.groupby([daily.index.year, daily.index.month]).apply(lambda s: s.index[-1])
    for (key, v), dt in zip(mo.items(), ds):
        out["curve"].append([str(dt.date()), round(float(v), 4), round(float(bser.loc[dt]), 4) if bser is not None else None])
    out["note"] = (f"조건: 신호 월간 평가, {a.rebalance}개월마다 리밸런싱, 점수 {a.min_score}↑ 상위 {a.top_n}종목 동일가중, 신호 다음 거래일 종가 체결, "
                   f"비용 가정(수수료 {a.commission*100:.3f}%·슬리피지 {a.slippage*100:.2f}% 편도, 매도세 {a.sell_tax*100:.2f}%), "
                   f"상폐 처리 손실 {a.delist_haircut*100:.0f}%. 상장폐지 종목 파일 포함 여부에 따라 생존편향이 남아 있을 수 있습니다. "
                   "과거 성과는 미래를 보장하지 않으며 점수 가중치는 이 결과에 맞춰 최적화하지 않았습니다.")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "backtest.json"))
    ap.add_argument("--rebalance", type=int, default=3)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--min-score", type=float, default=70)
    ap.add_argument("--commission", type=float, default=0.00015, help="편도 수수료율 (가정)")
    ap.add_argument("--slippage", type=float, default=0.001, help="편도 슬리피지 (가정)")
    ap.add_argument("--sell-tax", type=float, default=0.0020, help="매도 시 거래세 (가정 — 현행 세율 확인 후 입력)")
    ap.add_argument("--delist-haircut", type=float, default=0.0)
    ap.add_argument("--split", default="", help="표본 외 시작일 YYYY-MM-DD")
    a = ap.parse_args()
    res = run(a)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False))
