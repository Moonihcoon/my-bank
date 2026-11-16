"""KOSPI·KOSDAQ 전종목 → 산업 분류표(data/industry_map.csv)

입력
  data/krx_listed.csv       KRX Data Marketplace '상장종목 검색'/'전종목 기본정보' CSV 내려받기
                            (열 이름은 종목코드·종목명·시장구분·업종명 계열이면 자동 인식)
  data/industry_rules.csv   match_type(krx_sector|name_keyword), pattern, industry, priority  — 숫자가 작을수록 우선
  data/industry_overrides.csv  code,industry   — 사람이 확정한 값, 항상 최우선
규칙으로 못 정한 종목은 '미분류' 로 남긴다 → 대시보드에서 제외하거나 overrides 에 추가해 확정한다.
우선주·스팩·리츠는 기존 시세 자료와 같은 기준으로 제외한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ALIASES = {"code": ["종목코드", "단축코드", "code"], "name": ["종목명", "한글 종목약명", "name"],
           "market": ["시장구분", "시장", "market"], "sector": ["업종명", "소속부", "sector"]}


def find(df: pd.DataFrame, key: str) -> str | None:
    for c in ALIASES[key]:
        if c in df.columns:
            return c
    return None


def excluded(name: str) -> bool:
    return bool(re.search(r"(우$|우B$|우\(전환\)$|[0-9]우[A-Z]?$|스팩|제\d+호|리츠|REIT)", name))


def classify(row, rules: pd.DataFrame) -> tuple[str, str]:
    for r in rules.sort_values("priority").to_dict("records"):
        if r["match_type"] == "krx_sector" and isinstance(row["sector"], str) and r["pattern"] in row["sector"]:
            return r["industry"], f"규칙:업종 {r['pattern']}"
        if r["match_type"] == "name_keyword" and re.search(r["pattern"], row["name"]):
            return r["industry"], f"규칙:이름 {r['pattern']}"
    return "미분류", ""


def run() -> None:
    d = ROOT / "data"
    df = pd.read_csv(d / "krx_listed.csv", dtype=str)
    cols = {k: find(df, k) for k in ALIASES}
    miss = [k for k in ("code", "name", "market") if not cols[k]]
    if miss:
        raise SystemExit(f"krx_listed.csv 에서 열을 찾지 못함: {miss} (열: {list(df.columns)})")
    df = df.rename(columns={v: k for k, v in cols.items() if v})
    if "sector" not in df:
        df["sector"] = None
    df["code"] = df["code"].str.zfill(6)
    df = df[df["market"].str.contains("KOSPI|KOSDAQ|유가|코스", na=False)]
    df = df[~df["name"].apply(excluded)]
    rules = pd.read_csv(d / "industry_rules.csv")
    ov = pd.read_csv(d / "industry_overrides.csv", dtype={"code": str}).set_index("code")["industry"] if (d / "industry_overrides.csv").exists() else {}
    out = []
    for r in df.to_dict("records"):
        if r["code"] in ov:
            ind, src = ov[r["code"]], "확정(overrides)"
        else:
            ind, src = classify(r, rules)
        out.append({"code": r["code"], "name": r["name"], "market": "KOSPI" if "KOSPI" in r["market"] or "유가" in r["market"] else "KOSDAQ",
                    "industry": ind, "source": src})
    res = pd.DataFrame(out)
    res.to_csv(d / "industry_map_full.csv", index=False)
    res[res["industry"] != "미분류"].drop(columns="source").to_csv(d / "industry_map.csv", index=False)
    print(f"전체 {len(res)}종목 중 분류 {int((res.industry != '미분류').sum())}, 미분류 {int((res.industry == '미분류').sum())} "
          f"→ industry_map.csv(분류분), industry_map_full.csv(전체·근거 포함)")


if __name__ == "__main__":
    run()
