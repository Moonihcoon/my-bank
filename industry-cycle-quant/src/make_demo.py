"""화면 확인용 가상(합성) 데이터 생성. 실제 종목·시세가 아니며 투자 판단에 쓰면 안 된다."""
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent.parent / "data" / "demo"
(root / "prices").mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)

industries = ["조선(샘플)", "해저케이블(샘플)", "DRAM(샘플)", "NAND(샘플)", "철강(샘플)", "해운(샘플)"]
phases = ["전환", "상승", "상승", "횡보", "하락", "횡보"]
sig = pd.DataFrame({
    "industry": industries, "as_of": ["2026-10-31"] * 5 + ["2026-05-31"], "phase": phases,
    "inventory": [0.2, 0.1, 0.6, 0.0, -0.5, np.nan], "price": [0.3, 0.2, 0.7, -0.1, -0.4, 0.0],
    "orders": [0.5, 0.6, np.nan, 0.1, -0.3, 0.1], "supply": [0.2, -0.1, 0.4, -0.2, -0.6, 0.0]})
hist = []
for k, asof in enumerate(pd.date_range("2025-03-31", "2026-09-30", freq="QE")):
    t = sig.copy(); t["as_of"] = asof.strftime("%Y-%m-%d")
    for c in ["inventory", "price", "orders", "supply"]:
        t[c] = (t[c].fillna(0) + rng.normal(0, 0.3, len(t))).clip(-1, 1)
    hist.append(t)
pd.concat(hist + [sig]).to_csv(root / "industry_signals.csv", index=False)

rows, fun = [], []
dates = pd.bdate_range(end="2026-11-06", periods=320)
bench = 100 * np.cumprod(1 + rng.normal(0.0002, 0.01, len(dates)))
pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "close": bench}).to_csv(root / "benchmark.csv", index=False)
for i in range(18):
    code = f"9{i:05d}"
    ind = industries[i % 6]
    rows.append({"code": code, "name": f"샘플종목{chr(65 + i)}", "market": "KOSPI" if i % 3 else "KOSDAQ", "industry": ind})
    drift = rng.normal(0.0003, 0.0004)
    c = 10000 * np.cumprod(1 + rng.normal(drift, 0.018, len(dates)))
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                  "volume": 1e5, "value": c * 1e5 * rng.uniform(0.3, 3)}).to_csv(root / "prices" / f"{code}.csv", index=False)
    for asof in pd.date_range("2025-03-31", "2026-06-30", freq="QE"):
        fun.append({"code": code, "as_of": asof.strftime("%Y-%m-%d"), "op_margin_chg": rng.normal(0, 2.5), "est_revision": rng.normal(0, 6),
                    "fcf_positive": int(rng.random() > 0.35), "per_norm_pct": rng.uniform(5, 95),
                    "debt_ratio": rng.uniform(20, 250)})
pd.DataFrame(rows).to_csv(root / "industry_map.csv", index=False)
pd.DataFrame(fun).to_csv(root / "fundamentals.csv", index=False)
print("demo data ok")
