"""'상승률 200' 리서치 탭의 분봉 차트용 자료 만들기 → data/mn/YYYY-MM-DD.txt

- 리서치(data/rs)에 올라온 종목만, 게시일(주말·휴일이면 다음 거래일) 하루치 1분봉을 담습니다.
  (3분·5분·20분봉은 화면에서 이 1분봉을 묶어 만듭니다.)
- 원본: 저장소 옆 minute_all\\종목코드.parquet (열: time, open, high, low, close, volume)
- 파일 하나 = 하루치. 형식은 일봉 자료(px/m)와 같은 gzip+base64 JSON.
    {종목코드: {t0:첫 봉의 분(0~1439), d:[봉 사이 분], c:[첫 종가, 변화량…], o:[시가-직전종가…], h:[고가-종가…], l:[종가-저가…], v:[거래량…]}}
- 최근 7일 안의 날짜는 매번 다시 만들고(그날 분봉이 늦게 채워지므로), 그 이전 날짜는 이미 있으면 건너뜁니다.
"""
from __future__ import annotations
import base64, datetime, gzip, json, sys
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE)]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import REPO, load_panel, log  # noqa: E402

SRC = REPO.parent / 'minute_all'
OUT = REPO / 'data' / 'mn'
START = '2026-01-01'
REFRESH_DAYS = 7


def next_weekday(d: str) -> str:
    t = datetime.date.fromisoformat(d)
    while t.weekday() >= 5:
        t += datetime.timedelta(days=1)
    return t.isoformat()


def trade_day(d: str, days: list[str]) -> str:
    """게시일 이후 첫 거래일. 시세 자료 끝을 넘으면 첫 평일."""
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    return days[lo] if lo < len(days) else next_weekday(d)


def encode_day(df: pd.DataFrame) -> dict | None:
    """하루치 1분봉(time, open, high, low, close, volume) → 압축용 사전."""
    if df is None or len(df) == 0:
        return None
    df = df.sort_values('time')
    t = df['time']
    mins = (t.dt.hour * 60 + t.dt.minute).to_numpy(np.int64)
    c = df['close'].to_numpy(float)
    ok = (c > 0) & np.isfinite(c)
    if not ok.any():
        return None
    df, mins, c = df[ok], mins[ok], c[ok].round().astype(np.int64)
    o = df['open'].to_numpy(float).round().astype(np.int64)
    h = df['high'].to_numpy(float).round().astype(np.int64)
    l = df['low'].to_numpy(float).round().astype(np.int64)
    o = np.where(o > 0, o, c)
    h = np.maximum(h, np.maximum(o, c))
    l = np.where(l > 0, np.minimum(l, np.minimum(o, c)), np.minimum(o, c))
    v = df['volume'].fillna(0).to_numpy(float).round().astype(np.int64)
    return dict(t0=int(mins[0]), d=np.diff(mins).tolist(), c=[int(c[0])] + np.diff(c).tolist(),
                o=(o - c).tolist(), h=(h - c).tolist(), l=(c - l).tolist(), v=v.tolist())


def read_minute(code: str) -> pd.DataFrame | None:
    f = SRC / f'{code}.parquet'
    if not f.exists():
        return None
    df = pd.read_parquet(f, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    t = pd.to_datetime(df['time'])
    if getattr(t.dt, 'tz', None) is not None:
        t = t.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    df['time'] = t
    return df


def load_reports():
    out = []
    rs = REPO / 'data' / 'rs'
    for f in sorted(rs.glob('20??-??.json')):
        for r in json.loads(f.read_text(encoding='utf-8')):
            if r[4] >= START:
                out.append((str(r[1]).zfill(6), r[4]))
    return out


def main():
    reports = load_reports()
    if not reports:
        log('분봉 내보내기: 리서치 자료가 아직 없어 건너뜁니다.')
        return
    days = sorted({str(pd.Timestamp(x).date()) for x in load_panel()['date'].unique()})
    need: dict[str, set[str]] = {}
    for code, d in reports:
        need.setdefault(trade_day(d, days), set()).add(code)
    OUT.mkdir(parents=True, exist_ok=True)
    cutoff = (datetime.date.today() - datetime.timedelta(days=REFRESH_DAYS)).isoformat()
    todo = {T: cs for T, cs in need.items() if T >= cutoff or not (OUT / f'{T}.txt').exists()}
    if not todo:
        log(f'분봉 내보내기: 새로 만들 날짜가 없습니다. (전체 {len(need)}일)')
        return
    log(f'분봉 내보내기: {len(todo)}일 만들기 (전체 {len(need)}일, 폴더 {SRC})')
    if not SRC.exists():
        log('분봉 내보내기: minute_all 폴더가 없어 건너뜁니다.')
        return
    import time as _t
    newest = max((f.stat().st_mtime for f in SRC.glob('*.parquet')), default=0)
    if _t.time() - newest > 4 * 86400:
        # 분봉을 매일 받지 않는 PC(오래된 원본)에서 돌리면 이미 만들어진 날짜를 빈 값으로 덮어쓸 수 있어 건너뜁니다.
        log('분봉 내보내기: 이 PC의 분봉 원본이 4일 넘게 갱신되지 않아 건너뜁니다. (분봉을 받는 PC에서 만듭니다)')
        return
    by_code: dict[str, set[str]] = {}
    for T, cs in todo.items():
        for c in cs:
            by_code.setdefault(c, set()).add(T)
    res: dict[str, dict] = {T: {} for T in todo}
    miss = 0
    for k, (code, ds) in enumerate(sorted(by_code.items())):
        try:
            df = read_minute(code)
        except Exception as e:  # noqa: BLE001
            log(f'  분봉 읽기 실패 {code}: {type(e).__name__}: {e}')
            df = None
        if df is None:
            miss += len(ds)
            continue
        day = df['time'].dt.strftime('%Y-%m-%d')
        for T in ds:
            e = encode_day(df[day == T])
            if e:
                res[T][code] = e
            else:
                miss += 1
    n = 0
    for T, d in res.items():
        b = gzip.compress(json.dumps(d, separators=(',', ':')).encode(), 9, )
        (OUT / f'{T}.txt').write_text(base64.b64encode(b).decode(), encoding='ascii')
        n += len(d)
    log(f'분봉 내보내기 끝: {len(res)}일, 종목-날짜 {n}건, 분봉 없음 {miss}건')


if __name__ == '__main__':
    main()
