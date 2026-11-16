"""기존 일봉 수집 결과(export/csv/daily_*.csv + tickers.csv) → 이 프로젝트의 data 폴더 형식으로 변환

만드는 것 (--out 폴더 아래)
  prices/{code}.csv        ETF·ETN·우선주 제외 종목별 일봉 (date,open,high,low,close,volume,value)
  krx_listed.csv           종목코드,종목명,시장구분,업종명(없음)  → build_industry_map.py 입력
  krx_marketcap.csv        code,market_cap (마지막 관측값) → collect_dart.py 의 정상화 PER 입력
  benchmark.csv            date,close — **대용 지수**: KOSPI 종목의 전일 시가총액 가중 일간 수익률로 만든 지수
                           (실제 KOSPI 지수 파일이 없어서 대신 쓴다. 지수 파일을 받으면 같은 형식으로 교체)
상장폐지 종목이 원본에 없으므로 생존편향이 그대로 남는다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main(src: Path, out: Path) -> None:
    files = sorted((src / "csv").glob("daily_*.csv"))
    if not files:
        raise SystemExit(f"{src/'csv'} 에 daily_*.csv 가 없습니다")
    df = pd.concat([pd.read_csv(f, dtype={"ticker": str}, encoding="utf-8-sig") for f in files], ignore_index=True)
    t = pd.read_csv(src / "tickers.csv", dtype={"ticker": str}, encoding="utf-8-sig")
    keep = set(t[(t["is_etf"] == 0) & (t["is_pref"] == 0)]["ticker"])
    df = df[df["ticker"].isin(keep) & (df["is_etf"] == 0)].sort_values(["ticker", "date"])
    df = df.drop_duplicates(["ticker", "date"])
    (out / "prices").mkdir(parents=True, exist_ok=True)
    cols = ["date", "open", "high", "low", "close", "volume", "value"]
    for code, g in df.groupby("ticker"):
        g[cols].to_csv(out / "prices" / f"{code}.csv", index=False)

    meta = df.groupby("ticker").agg(name=("name", "last"), market=("market", "last")).reset_index()
    pd.DataFrame({"종목코드": meta["ticker"], "종목명": meta["name"], "시장구분": meta["market"], "업종명": ""}).to_csv(
        out / "krx_listed.csv", index=False)
    mc = df.dropna(subset=["market_cap_won"]).groupby("ticker")["market_cap_won"].last()
    mc.rename("market_cap").rename_axis("code").reset_index().to_csv(out / "krx_marketcap.csv", index=False)

    # 대용 지수: KOSPI 종목의 전일 시가총액 가중 수익률 (시총 없는 종목은 제외). 실제 KOSPI 지수와 다를 수 있다.
    kospi = df[df["market"] == "KOSPI"]
    px = kospi.pivot(index="date", columns="ticker", values="close")
    mc_w = kospi.pivot(index="date", columns="ticker", values="market_cap_won").ffill().shift(1)
    ret = px.pct_change(fill_method=None).clip(-0.3, 0.3)
    w = mc_w.where(ret.notna())
    idx_ret = (ret * w).sum(axis=1) / w.sum(axis=1)
    idx_ret = idx_ret.fillna(0)
    pd.DataFrame({"date": idx_ret.index, "close": 100 * (1 + idx_ret).cumprod()}).to_csv(out / "benchmark.csv", index=False)
    print(f"종목 {df['ticker'].nunique()}개, {df['date'].min()} ~ {df['date'].max()}, 행 {len(df):,} → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="export 폴더 (csv/ 와 tickers.csv 가 있는 곳)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data"))
    a = ap.parse_args()
    main(Path(a.src), Path(a.out))
