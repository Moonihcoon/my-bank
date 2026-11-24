"""코스피·코스닥 지수 자료 만들기 → data/ix/  ('상승률 200' 지수차트 탭용)

받는 곳: 키움 REST 업종 차트  일봉 ka20006 · 분봉 ka20005  (업종코드 001 코스피, 101 코스닥)
  data/ix/d.txt          2016-01-01부터의 일봉(시·고·저·종·거래대금[억원]) gzip+base64 JSON {"k":[...],"q":[...]}
  data/ix/m/YYYY-MM-DD.txt  하루치 1분봉 gzip+base64 JSON {"k":{t0,d,c,o,h,l,v,s,vk},"q":{...}}
  data/ix/meta.json      분봉이 있는 날짜 목록 등
  data/ix/_daily.json    일봉 원본(다음 실행에서 새로 생긴 부분만 받기 위한 저장분, 공개하지 않음)
월봉은 화면에서 일봉을 묶어 만듭니다.
"""
from __future__ import annotations
import base64, datetime, gzip, json, statistics, sys, time
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE)]
from common import REPO, kiwoom_keys, log  # noqa: E402
from kiwoom_api import Kiwoom, to_num  # noqa: E402

OUT = REPO / 'data' / 'ix'
MKT = {'k': ('001', '코스피'), 'q': ('101', '코스닥')}
START = '20160101'
MIN_KEEP_DAYS = 8          # 이 기간 안의 분봉 날짜는 매번 다시 만듭니다(그날 마지막 봉이 늦게 채워질 수 있음)


def gz(o) -> str:
    return base64.b64encode(gzip.compress(json.dumps(o, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))).decode('ascii')


def first_list(j):
    for k, v in j.items():
        if isinstance(v, list):
            return v
    return []


def pull(api, api_id, body, date_of, stop_before, max_pages):
    """연속조회로 최신 → 과거로 받습니다. date_of(rec)가 stop_before 이전이 나오면 멈춥니다."""
    out, cont, nkey = [], None, None
    for _ in range(max_pages):
        j, cont, nkey = api.call(api_id, '/api/dostk/chart', body, cont, nkey)
        recs = first_list(j)
        if not recs:
            break
        if not out:
            log(f'  {api_id} 응답 항목: ' + json.dumps(recs[0], ensure_ascii=False)[:300])
        out.extend(recs)
        ds = [date_of(r) for r in recs if date_of(r)]
        if (ds and min(ds) < stop_before) or cont != 'Y':
            break
    return out


def scale_of(closes):
    """지수가 100배 정수로 오는 경우를 알아냅니다(코스피·코스닥은 2016년 이후 항상 2만 미만)."""
    c = [x for x in closes if x == x and x > 0]
    return 100.0 if c and statistics.median(c) > 20000 else 1.0


def value_to_eok(vals):
    """거래대금 단위를 추정해 억원 환산 배수를 돌려줍니다. (백만원이면 0.01, 억원이면 1)"""
    v = [x for x in vals if x == x and x > 0]
    if not v:
        return 0.01
    med = statistics.median(v)
    return 0.01 if med > 5e5 else 1.0


def daily_rows(recs):
    rows = {}
    for r in recs:
        d = str(r.get('dt') or '').strip()
        if len(d) != 8:
            continue
        o, h, l, c = (abs(to_num(r.get(k))) for k in ('open_pric', 'high_pric', 'low_pric', 'cur_prc'))
        if not (c == c and c > 0):
            continue
        rows[d] = [d, o, h, l, c, abs(to_num(r.get('trde_prica')))]
    return rows


def update_daily(api, now_ok_today):
    OUT.mkdir(parents=True, exist_ok=True)
    store = {}
    p = OUT / '_daily.json'
    if p.exists():
        try:
            store = json.loads(p.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001
            store = {}
    today = datetime.date.today().strftime('%Y%m%d')
    res = {}
    for key, (code, nm) in MKT.items():
        have = store.get(key, {})
        last = max(have) if have else None
        stop = START if not last else (datetime.datetime.strptime(last, '%Y%m%d') - datetime.timedelta(days=10)).strftime('%Y%m%d')
        recs = pull(api, 'ka20006', {'inds_cd': code, 'base_dt': today}, lambda r: str(r.get('dt') or ''), stop, 80)
        new = daily_rows(recs)
        if not new:
            log(f'지수 일봉 {nm}: 받은 자료가 없습니다. (키움 응답 형식이 달라졌을 수 있습니다)')
            res[key] = have
            continue
        sc = scale_of([v[4] for v in new.values()])
        ve = value_to_eok([v[5] for v in new.values()])
        for d, v in new.items():
            have[d] = [d, round(v[1] / sc, 2), round(v[2] / sc, 2), round(v[3] / sc, 2), round(v[4] / sc, 2), round(v[5] * ve, 1)]
        if not now_ok_today:
            have.pop(today, None)       # 장중·장 마감 직후에는 오늘 봉이 미완성
        store[key] = have
        res[key] = have
        log(f'지수 일봉 {nm}: {len(new)}건 받음 (배율 {sc:g}, 거래대금 환산 {ve:g}) → 전체 {len(have)}일, {min(have)}~{max(have)}')
    p.write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
    out = {k: [[int(d), *v[1:]] for d, v in sorted(rows.items()) if d >= START] for k, rows in res.items()}
    (OUT / 'd.txt').write_text(gz(out), encoding='ascii')
    return out


def encode_day(bars, sc, ve, vk):
    """bars: [(분(0~1439), o,h,l,c, vol, val)] 시간순 → 하루치 압축 형식."""
    S = 100
    t = [b[0] for b in bars]
    ci = [round(b[4] / sc * S) for b in bars]
    d = {'t0': t[0], 'd': [t[i] - t[i - 1] for i in range(1, len(t))],
         'c': [ci[0]] + [ci[i] - ci[i - 1] for i in range(1, len(ci))],
         'o': [round(b[1] / sc * S) - (ci[i - 1] if i else ci[0]) for i, b in enumerate(bars)],
         'h': [round(b[2] / sc * S) - ci[i] for i, b in enumerate(bars)],
         'l': [ci[i] - round(b[3] / sc * S) for i, b in enumerate(bars)],
         's': S, 'vk': vk}
    d['v'] = [round(b[6] * ve * 100) if vk == 'a' else int(b[5] * 1000) for b in bars]   # 'a': 억원×100(=백만원), 'v': 주 (키움 업종 거래량은 천주 단위)
    return d


def update_minute(api, now_ok_today):
    mdir = OUT / 'm'
    mdir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    stop = (today - datetime.timedelta(days=MIN_KEEP_DAYS)).strftime('%Y%m%d')
    first_run = not any(mdir.glob('*.txt'))
    if first_run:
        stop = '20000101'
    per = {}   # date -> {key: bars}
    cfg = {}
    for key, (code, nm) in MKT.items():
        recs = pull(api, 'ka20005', {'inds_cd': code, 'tic_scope': '1'}, lambda r: str(r.get('cntr_tm') or '')[:8], stop, 400)
        if not recs:
            log(f'지수 분봉 {nm}: 받은 자료가 없습니다.')
            continue
        cl = [abs(to_num(r.get('cur_prc'))) for r in recs]
        sc = scale_of(cl)
        hasval = any(abs(to_num(r.get('trde_prica'))) > 0 for r in recs[:50])
        vals = [abs(to_num(r.get('trde_prica'))) for r in recs if abs(to_num(r.get('trde_prica'))) > 0]
        ve = value_to_eok(vals) if hasval else 0.01
        vk = 'a' if hasval else 'v'
        seen = set()
        for r in recs:
            tm = str(r.get('cntr_tm') or '')
            if len(tm) < 12 or tm in seen:
                continue
            seen.add(tm)
            c = abs(to_num(r.get('cur_prc')))
            if not (c == c and c > 0):
                continue
            o, h, l = (abs(to_num(r.get(k))) for k in ('open_pric', 'high_pric', 'low_pric'))
            mi = int(tm[8:10]) * 60 + int(tm[10:12])
            if not (540 <= mi <= 940):
                continue
            per.setdefault(tm[:8], {}).setdefault(key, []).append(
                (mi, o if o == o and o > 0 else c, h if h == h and h > 0 else c, l if l == l and l > 0 else c, c,
                 abs(to_num(r.get('trde_qty'))), abs(to_num(r.get('trde_prica'))) if hasval else 0))
        ds = sorted({str(r.get('cntr_tm') or '')[:8] for r in recs})
        log(f'지수 분봉 {nm}: {len(recs)}건 받음 (배율 {sc:g}, {"거래대금" if hasval else "거래량만"}) {ds[0]}~{ds[-1]}')
        cfg[key] = (sc, ve, vk)
    made = 0
    for d, mk in sorted(per.items()):
        day = datetime.datetime.strptime(d, '%Y%m%d').date()
        if day == today and not now_ok_today:
            continue
        out = {}
        for key, bars in mk.items():
            bars.sort()
            if len(bars) < 5:
                continue
            sc, ve, vk = cfg[key]
            out[key] = encode_day(bars, sc, ve, vk)
        if not out:
            continue
        (mdir / f'{day.isoformat()}.txt').write_text(gz(out), encoding='ascii')
        made += 1
    log(f'지수 분봉: {made}일 저장')


def main():
    k, s = kiwoom_keys()
    if not k or not s:
        log('지수 자료: 키움 키가 없어 건너뜁니다.')
        return
    now = datetime.datetime.now()
    now_ok_today = now.weekday() < 5 and (now.hour, now.minute) >= (15, 40) or now.weekday() >= 5
    api = Kiwoom(k, s)
    try:
        update_daily(api, now_ok_today)
    except Exception as e:  # noqa: BLE001
        log(f'지수 일봉 오류: {type(e).__name__}: {e}')
    try:
        update_minute(api, now_ok_today)
    except Exception as e:  # noqa: BLE001
        log(f'지수 분봉 오류: {type(e).__name__}: {e}')
    days = sorted(p.stem for p in (OUT / 'm').glob('*.txt')) if (OUT / 'm').exists() else []
    meta = {'minute_days': days, 'updated': now.strftime('%Y-%m-%d %H:%M')}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


if __name__ == '__main__':
    main()
