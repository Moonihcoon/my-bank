"""산업 지표 수집 → data/industry_signals.csv (시점별 이력)

data/signal_sources.csv 에 적힌 시계열을 받아 신호(-1~+1)로 바꾼다. 행 하나 = 시계열 하나.
  enabled     1 일 때만 수집
  industry    industry_map.csv 의 산업명과 동일
  signal      inventory | price | orders | supply   (점수 계산에 쓰이는 4개 신호)
  provider    fred | ecos | kosis | csv
  series_id   fred: 시리즈 ID / ecos: 통계코드/주기/항목코드1 (예: 901Y033/M/A) / kosis: 'URL생성'으로 만든 전체 URL(키 제외) / csv: 파일 경로
  direction   +1 이면 값이 오를수록 좋음, -1 이면 오를수록 나쁨(예: 재고 수준)
  scale       3개월 평균이 직전 12개월 평균 대비 이 비율만큼 변하면 ±1 (기본 0.10)
  lag_days    공표 지연일. as_of = 관측월말 + lag_days (그 전에는 신호를 쓰지 않음 → 미래참조 방지)

키(환경변수): FRED_API_KEY, ECOS_API_KEY, KOSIS_API_KEY (모두 무료 발급, 저장소에 넣지 말 것)
국면(phase)은 신호 평균과 3개월 변화로 자동 판정하는 초안 규칙이며, 직접 수정한 값은 data/phase_override.csv(industry,as_of,phase)로 덮어쓴다.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
SIGNALS = ["inventory", "price", "orders", "supply"]


def fetch_fred(sid: str) -> pd.Series:
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": sid, "api_key": os.environ["FRED_API_KEY"], "file_type": "json"}, timeout=30)
    r.raise_for_status()
    o = [(x["date"], x["value"]) for x in r.json()["observations"] if x["value"] != "."]
    return pd.Series([float(v) for _, v in o], index=pd.to_datetime([d for d, _ in o]))


def fetch_ecos(spec: str) -> pd.Series:
    stat, cycle, item = (spec.split("/") + [""])[:3]
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{os.environ['ECOS_API_KEY']}/json/kr/1/10000/{stat}/{cycle}/200001/{pd.Timestamp.today():%Y%m}/{item}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    rows = r.json()["StatisticSearch"]["row"]
    idx = pd.to_datetime([x["TIME"][:6] + "01" for x in rows], format="%Y%m%d")  # 월 주기 가정
    return pd.Series([float(x["DATA_VALUE"]) for x in rows], index=idx)


def fetch_kosis(url: str) -> pd.Series:
    r = requests.get(url, params={"apiKey": os.environ["KOSIS_API_KEY"]} if "apiKey" not in url else None, timeout=30)
    r.raise_for_status()
    rows = r.json()
    idx = pd.to_datetime([x["PRD_DE"][:6] + "01" for x in rows], format="%Y%m%d")
    return pd.Series([float(x["DT"]) for x in rows], index=idx).groupby(level=0).sum()


def fetch_csv(path: str) -> pd.Series:
    df = pd.read_csv(ROOT / path if not Path(path).is_absolute() else path, parse_dates=["date"])
    return df.set_index("date")["value"].astype(float)


FETCH = {"fred": fetch_fred, "ecos": fetch_ecos, "kosis": fetch_kosis, "csv": fetch_csv}


def to_signal(s: pd.Series, direction: float, scale: float) -> pd.Series:
    """월말 기준: (최근 3개월 평균 / 직전 12개월 평균 − 1)을 scale 로 나눠 -1~+1 로 자른다."""
    m = s.resample("ME").last().dropna()
    recent = m.rolling(3).mean()
    prior = m.shift(3).rolling(12).mean()
    chg = recent / prior - 1
    return (direction * chg / scale).clip(-1, 1).dropna()


def phase_of(c: float, dc: float) -> str:
    if c >= 0.3:
        return "상승"
    if dc > 0.15:
        return "전환"
    if c <= -0.2:
        return "하락"
    return "횡보"


def run() -> None:
    src = pd.read_csv(ROOT / "data" / "signal_sources.csv")
    src = src[src["enabled"] == 1]
    per_ind: dict[str, dict[str, pd.Series]] = {}
    lags: dict[str, int] = {}
    for r in src.to_dict("records"):
        try:
            raw = FETCH[r["provider"]](str(r["series_id"]))
            sig = to_signal(raw, float(r.get("direction", 1)), float(r.get("scale", 0.10) or 0.10))
        except Exception as e:  # noqa: BLE001
            print(f"[실패] {r['industry']}/{r['signal']} ({r['provider']}): {e}")
            continue
        per_ind.setdefault(r["industry"], {})[r["signal"]] = sig
        lags[r["industry"]] = max(lags.get(r["industry"], 0), int(r.get("lag_days", 30) or 30))
    out = []
    for ind, d in per_ind.items():
        df = pd.DataFrame(d).sort_index()
        comp = df.mean(axis=1)
        dc = comp - comp.shift(3)
        for t in df.index:
            row = {"industry": ind, "as_of": (t + pd.Timedelta(days=lags[ind])).date().isoformat(),
                   "phase": phase_of(comp[t], dc[t] if pd.notna(dc[t]) else 0.0)}
            for k in SIGNALS:
                row[k] = round(float(df[k][t]), 3) if k in df and pd.notna(df[k][t]) else np.nan
            out.append(row)
    if not out:
        print("수집된 신호 없음 — signal_sources.csv 의 enabled 와 API 키를 확인하세요.")
        return
    res = pd.DataFrame(out)
    ov = ROOT / "data" / "phase_override.csv"
    if ov.exists():
        o = pd.read_csv(ov)
        res = res.merge(o, on=["industry", "as_of"], how="left", suffixes=("", "_o"))
        res["phase"] = res["phase_o"].fillna(res["phase"])
        res = res.drop(columns="phase_o")
    res.to_csv(ROOT / "data" / "industry_signals.csv", index=False)
    print(f"industry_signals.csv {len(res)}행 ({res['industry'].nunique()}개 산업)")


if __name__ == "__main__":
    run()
