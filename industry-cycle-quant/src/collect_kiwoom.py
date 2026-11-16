"""키움 REST API 일봉(ka10081) 수집기.

- 앱키/시크릿키는 환경변수 KIWOOM_APPKEY, KIWOOM_SECRETKEY 로만 읽는다 (코드·채팅·저장소에 넣지 말 것).
- 장 마감 후 하루 1회 실행해 data/prices/{종목코드}.csv 에 누적한다.
- 호출 한도는 공식 문서에서 현재 값을 확인해 CALLS_PER_SEC 에 반영한다.
  (기존 문서 안내: 국내주식 조회 초당 5회 → 보수적으로 4회로 설정)
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

BASE = os.environ.get("KIWOOM_BASE", "https://api.kiwoom.com")  # 모의: https://mockapi.kiwoom.com
CALLS_PER_SEC = float(os.environ.get("KIWOOM_CALLS_PER_SEC", "4"))
PRICE_DIR = Path(__file__).resolve().parent.parent / "data" / "prices"
FIELDS = ["date", "open", "high", "low", "close", "volume", "value"]

_last_call = 0.0


def _throttle() -> None:
    global _last_call
    gap = 1.0 / CALLS_PER_SEC
    wait = _last_call + gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def get_token() -> str:
    appkey = os.environ["KIWOOM_APPKEY"]
    secret = os.environ["KIWOOM_SECRETKEY"]
    r = requests.post(
        f"{BASE}/oauth2/token",
        json={"grant_type": "client_credentials", "appkey": appkey, "secretkey": secret},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("return_code") not in (0, None):
        raise RuntimeError(f"토큰 발급 실패: {data.get('return_msg')}")
    return data["token"]


def fetch_daily(token: str, code: str, base_dt: str, max_pages: int = 50, retries: int = 3):
    """종목 1개의 일봉을 연속조회(cont-yn/next-key)로 받아 최신순 리스트로 반환."""
    rows, cont, nkey = [], "N", ""
    for _ in range(max_pages):
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": "ka10081",
        }
        if cont == "Y":
            headers.update({"cont-yn": "Y", "next-key": nkey})
        body = {"stk_cd": code, "base_dt": base_dt, "upd_stkpc_tp": "1"}  # 1 = 수정주가
        for attempt in range(retries):
            _throttle()
            r = requests.post(f"{BASE}/api/dostk/chart", headers=headers, json=body, timeout=15)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError(f"{code}: 재시도 초과(429)")
        data = r.json()
        if data.get("return_code") not in (0, None):  # 업무 오류도 HTTP 200 으로 온다
            raise RuntimeError(f"{code}: {data.get('return_msg')}")
        rows += data.get("stk_dt_pole_chart_qry", [])
        cont, nkey = r.headers.get("cont-yn", "N"), r.headers.get("next-key", "")
        if cont != "Y":
            return rows, True
    return rows, False  # 페이지 한도에서 잘림


def _num(x) -> float:
    return abs(float(str(x).replace(",", "") or 0))  # 키움은 등락 부호가 +/- 로 붙는 경우가 있다


def merge_save(code: str, rows) -> int:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    path = PRICE_DIR / f"{code}.csv"
    existing = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            existing = {r["date"]: r for r in csv.DictReader(f)}
    for r in rows:
        d = r["dt"]
        existing[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = {
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "open": _num(r["open_pric"]), "high": _num(r["high_pric"]),
            "low": _num(r["low_pric"]), "close": _num(r["cur_prc"]),
            "volume": _num(r["trde_qty"]), "value": _num(r.get("trde_prica", 0)),
        }
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(existing):
            w.writerow(existing[k])
    return len(existing)


def last_saved(code: str) -> str | None:
    path = PRICE_DIR / f"{code}.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        dates = [r["date"] for r in csv.DictReader(f)]
    return dates[-1] if dates else None


def main(codes: list[str]) -> int:
    token = get_token()
    today = date.today().strftime("%Y%m%d")
    ok = fail = truncated = 0
    log = []
    for code in codes:
        try:
            rows, complete = fetch_daily(token, code, today)
            # 이미 받은 날짜 이후만 필요하면 여기서 필터링 가능 (수정주가 반영을 위해 전체 갱신이 기본)
            n = merge_save(code, rows)
            ok += 1
            truncated += (not complete)
            log.append((code, "ok" if complete else "truncated", n))
        except Exception as e:  # noqa: BLE001 - 종목 단위로 실패를 기록하고 계속
            fail += 1
            log.append((code, f"error: {e}", 0))
    out = PRICE_DIR.parent / "collect_log.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "status", "rows"])
        w.writerows(log)
    print(f"성공 {ok} / 실패 {fail} / 잘림 {truncated}")
    return 1 if fail else 0


if __name__ == "__main__":
    codes_arg = sys.argv[1:] or [r["code"] for r in csv.DictReader(
        (Path(__file__).resolve().parent.parent / "data" / "industry_map.csv").open(encoding="utf-8"))]
    sys.exit(main(codes_arg))
