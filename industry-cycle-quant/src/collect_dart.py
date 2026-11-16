"""OpenDART 재무 수집 → data/fundamentals.csv (시점별 이력 포함)

환경변수 DART_API_KEY (opendart.fss.or.kr 에서 무료 발급, 비공개 보관).
- 종목코드→corp_code: corpCode.xml (zip)
- 분기/반기/사업보고서 주요계정: fnlttSinglAcnt.json  → 영업이익률 전년동기 대비(%p), 부채비율
- 연간 현금흐름: fnlttSinglAcntAll.json (사업보고서) → FCF = 영업활동현금흐름 − 유형자산 취득
- avail(사용 가능일) = 공시 접수일(rcept_no 앞 8자리). 백테스트에서 미래참조를 막는 핵심 열이다.
- 일일 한도(키당 약 20,000건, 초과 시 status 020)에 맞춰 --max-calls 로 끊고 캐시(data/dart_cache)로 이어받는다.
  3,400종목 × 7년 전체 적재는 며칠에 나눠 돌린다.
- est_revision(실적 추정치 변화)은 무료 공식 출처가 없어 비워 둔다 → 점수에서 '미확인'으로 처리된다.
- per_norm_pct: data/krx_marketcap.csv(code,market_cap — KRX Data Marketplace 에서 내려받은 시가총액) 이 있으면
  시가총액 / 최근 3개 사업연도 평균 당기순이익(양수일 때)의 산업 내 백분위를 '최신 행에만' 채운다(과거 시점 시총이 없어 백테스트 누수 방지).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BASE = "https://opendart.fss.or.kr/api"
ROOT = Path(__file__).resolve().parent.parent
REPRT = {"11013": "03-31", "11012": "06-30", "11014": "09-30", "11011": "12-31"}
calls = 0


def key() -> str:
    return os.environ["DART_API_KEY"]


def get_json(path: str, params: dict, cache: Path, max_calls: int):
    global calls
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    if calls >= max_calls:
        raise StopIteration("일일 호출 상한 도달")
    calls += 1
    time.sleep(0.12)
    r = requests.get(f"{BASE}/{path}", params={"crtfc_key": key(), **params}, timeout=20)
    r.raise_for_status()
    data = r.json()
    st = data.get("status")
    if st == "020":
        raise StopIteration("OpenDART 한도 초과(020)")
    if st not in ("000", "013"):  # 013 = 조회된 데이터 없음 (정상)
        raise RuntimeError(f"DART 오류 {st}: {data.get('message')}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def corp_codes(cache_dir: Path) -> dict[str, str]:
    p = cache_dir / "corp_codes.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    r = requests.get(f"{BASE}/corpCode.xml", params={"crtfc_key": key()}, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    m = {}
    for e in root.iter("list"):
        sc = (e.findtext("stock_code") or "").strip()
        if sc:
            m[sc] = e.findtext("corp_code").strip()
    cache_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m), encoding="utf-8")
    return m


def amt(s) -> float | None:
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick(rows: list[dict], names: list[str], sj: tuple[str, ...] = ("IS", "CIS", "BS", "CF")):
    """계정명 후보 중 먼저 매칭되는 행(연결 우선)."""
    for fs in ("CFS", "OFS"):
        for n in names:
            for r in rows:
                if r.get("fs_div", fs) == fs and r.get("sj_div") in sj and r.get("account_nm", "").replace(" ", "").startswith(n):
                    return r
    return None


def parse_main(rows: list[dict]) -> dict | None:
    """fnlttSinglAcnt 응답 → 영업이익률(당기/전기), 부채비율, 순이익, 접수일."""
    if not rows:
        return None
    sales = pick(rows, ["매출액", "수익(매출액)", "영업수익"], ("IS", "CIS"))
    op = pick(rows, ["영업이익"], ("IS", "CIS"))
    debt = pick(rows, ["부채총계"], ("BS",))
    eq = pick(rows, ["자본총계"], ("BS",))
    ni = pick(rows, ["당기순이익"], ("IS", "CIS"))
    out = {"rcept": re.sub(r"\D", "", rows[0].get("rcept_no", ""))[:8]}
    if sales and op:
        s0, s1, o0, o1 = amt(sales.get("thstrm_amount")), amt(sales.get("frmtrm_amount")), amt(op.get("thstrm_amount")), amt(op.get("frmtrm_amount"))
        if s0 and s1 and o0 is not None and o1 is not None:
            out["op_margin_chg"] = round((o0 / s0 - o1 / s1) * 100, 2)  # %p
    if debt and eq:
        d, e = amt(debt.get("thstrm_amount")), amt(eq.get("thstrm_amount"))
        if d is not None and e and e > 0:
            out["debt_ratio"] = round(d / e * 100, 1)
    if ni:
        out["net_income"] = amt(ni.get("thstrm_amount"))
    return out


def parse_fcf(rows: list[dict]) -> int | None:
    cfo = pick(rows, ["영업활동현금흐름", "영업활동으로인한현금흐름"], ("CF",))
    capex = pick(rows, ["유형자산의취득", "유형자산취득"], ("CF",))
    if not cfo:
        return None
    o = amt(cfo.get("thstrm_amount"))
    c = amt(capex.get("thstrm_amount")) if capex else 0.0
    if o is None:
        return None
    return int(o - abs(c or 0) > 0)


def run(a) -> None:
    cache = ROOT / "data" / "dart_cache"
    imap = pd.read_csv(ROOT / "data" / "industry_map.csv", dtype={"code": str})
    cc = corp_codes(cache)
    this_year = date.today().year
    rows_out, done_all = [], True
    try:
        for r in imap.to_dict("records"):
            corp = cc.get(r["code"])
            if not corp:
                print(f"{r['code']} {r['name']}: corp_code 없음(상장폐지/신규 가능)")
                continue
            for y in range(this_year - a.years, this_year + 1):
                fcf = None
                for rc, md in REPRT.items():
                    d = get_json("fnlttSinglAcnt.json", {"corp_code": corp, "bsns_year": y, "reprt_code": rc},
                                 cache / f"{corp}_{y}_{rc}.json", a.max_calls)
                    if d.get("status") != "000":
                        continue
                    m = parse_main(d["list"])
                    if not m:
                        continue
                    if rc == "11011":
                        cf = get_json("fnlttSinglAcntAll.json", {"corp_code": corp, "bsns_year": y, "reprt_code": rc, "fs_div": "CFS"},
                                      cache / f"{corp}_{y}_CF.json", a.max_calls)
                        if cf.get("status") == "000":
                            fcf = parse_fcf(cf["list"])
                    rows_out.append({"code": r["code"], "as_of": f"{y}-{md}", "avail": m["rcept"] and f"{m['rcept'][:4]}-{m['rcept'][4:6]}-{m['rcept'][6:]}",
                                     "op_margin_chg": m.get("op_margin_chg"), "est_revision": None,
                                     "fcf_positive": fcf if rc == "11011" else None, "per_norm_pct": None,
                                     "debt_ratio": m.get("debt_ratio"), "net_income": m.get("net_income") if rc == "11011" else None})
    except StopIteration as e:
        done_all = False
        print(f"중단: {e} — 캐시가 남아 있으니 다음 날 같은 명령으로 이어서 실행하세요 (이번 호출 {calls}건).")
    if not rows_out:
        return
    df = pd.DataFrame(rows_out).sort_values(["code", "as_of"])
    # 연간 FCF 는 다음 연간 공시 전까지 이어서 사용(공시 시점 이후에만 유효하도록 avail 은 그대로)
    df["fcf_positive"] = df.groupby("code")["fcf_positive"].ffill()
    kp = ROOT / "data" / "krx_marketcap.csv"
    if kp.exists():
        mc = pd.read_csv(kp, dtype={"code": str}).set_index("code")["market_cap"]
        ann = df.dropna(subset=["net_income"]).groupby("code")["net_income"].apply(lambda s: s.tail(3).mean())
        pe = (mc.reindex(ann.index) / ann).where(ann > 0)
        ind = imap.set_index("code")["industry"]
        pct = pe.groupby(ind.reindex(pe.index)).rank(pct=True) * 100
        last = df.groupby("code").tail(1).index
        df.loc[last, "per_norm_pct"] = df.loc[last, "code"].map(pct)
    df.drop(columns=["net_income"]).to_csv(ROOT / "data" / "fundamentals.csv", index=False)
    print(f"fundamentals.csv {len(df)}행 저장 (완료={done_all}, 호출 {calls}건)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--max-calls", type=int, default=18000)
    run(ap.parse_args())
