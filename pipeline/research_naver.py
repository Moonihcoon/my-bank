"""네이버 증권 '리서치 > 국내종목(종목분석)' 수집 → data/rs/ (상승률 200 '리서치' 탭용)

받는 곳(네이버 모바일 증권이 화면에 쓰는 주소, 로그인 필요 없음):
  목록  https://m.stock.naver.com/api/research/company?page=N&pageSize=M
  상세  https://m.stock.naver.com/api/research/company/<리서치번호>
저장:  data/rs/YYYY-MM.json  (월별 리포트 목록)   data/rs/index.json (날짜별 건수)   data/rs/_state.json
항목:  [번호, 종목코드, 종목명, 증권사, 게시일, 제목, 투자의견(원문), 의견(매수/중립/매도/없음), 목표주가, 게시 전일 종가, 요약]

- 2026-01-01 이후 리포트를 모읍니다. 첫 실행은 오래 걸려서 시간 제한([research] minutes, 기본 20분) 안에서
  새것부터 받고, 다음 실행에서 이어서 받습니다. (한 번에 다 받으려면 RESEARCH_MINUTES=150 으로 실행)
- 요약은 본문 첫 부분 약 230자만 보관합니다. 전문은 '원문' 링크(네이버 증권)로 보냅니다.
- 네이버가 주소를 바꾸면 수집이 멈추고 로그에 남습니다. 이미 모은 내용은 그대로 보입니다.
"""
from __future__ import annotations
import datetime, html as _html, json, re, sys, time, urllib.error, urllib.request
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE)]
from common import REPO, opt, log  # noqa: E402

START = '2026-01-01'
LIST = 'https://m.stock.naver.com/api/research/company?page={p}&pageSize={n}'
DETAIL = 'https://m.stock.naver.com/api/research/company/{i}'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
OUT = REPO / 'data' / 'rs'
SUM_MAX = 230


def get_json(url, tries=3):
    err = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                                                       'Referer': 'https://m.stock.naver.com/'})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err = e
            if e.code == 429:
                time.sleep(30)
            elif e.code in (400, 404):
                break
            else:
                time.sleep(2 + 3 * k)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + 3 * k)
    raise RuntimeError(f'{type(err).__name__}: {err}')


def norm_opinion(s: str) -> str:
    t = (s or '').strip().lower().replace(' ', '')
    if not t:
        return '없음'
    if any(k in t for k in ('매수', 'buy', 'outperform', '비중확대', 'overweight', 'add', '적극')):
        return '매수'
    if any(k in t for k in ('매도', 'sell', 'underperform', '비중축소', 'underweight', 'reduce')):
        return '매도'
    if any(k in t for k in ('중립', 'hold', 'neutral', 'marketperform', 'trading', '보유', '시장수익률', '시장평균')):
        return '중립'
    return '없음'


def summarize(content: str) -> str:
    """본문 HTML → 2~3줄 분량(약 230자)의 평문 요약."""
    if not content:
        return ''
    t = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>', '\n', content)
    t = re.sub(r'<[^>]+>', '', t)
    lines = [re.sub(r'\s+', ' ', _html.unescape(x)).strip() for x in t.split('\n')]
    lines = [x for x in lines if x]
    # 첫 줄이 문장이 아닌 소제목(짧고 마침표 없음)이면 건너뜁니다.
    if len(lines) > 1 and len(lines[0]) <= 70 and not re.search(r'[.다요]$', lines[0]):
        lines = lines[1:]
    s = ' '.join(lines)
    if len(s) <= SUM_MAX:
        return s
    cut = s[:SUM_MAX]
    m = list(re.finditer(r'(다|음|함|임|됨)\.\s', cut + ' '))
    if m and m[-1].end() >= 90:
        return cut[:m[-1].end()].strip()
    return cut.rstrip() + '…'


def to_int(v):
    try:
        n = int(float(str(v).replace(',', '')))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


# ---------- 저장소 ----------
def load_store():
    st = {}
    if OUT.exists():
        for f in sorted(OUT.glob('20??-??.json')):
            try:
                for r in json.loads(f.read_text(encoding='utf-8')):
                    st[r[0]] = r
            except Exception as e:  # noqa: BLE001
                log(f'리서치 저장 파일 읽기 실패 {f.name}: {e}')
    state = {}
    p = OUT / '_state.json'
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001
            state = {}
    return st, state


def save_store(st, state):
    OUT.mkdir(parents=True, exist_ok=True)
    by = {}
    for r in st.values():
        by.setdefault(r[4][:7], []).append(r)
    for ym, rows in by.items():
        rows.sort(key=lambda r: (r[4], r[0]), reverse=True)
        (OUT / f'{ym}.json').write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    cnt = {}
    for r in st.values():
        cnt[r[4]] = cnt.get(r[4], 0) + 1
    idx = {'dates': sorted(cnt.items(), reverse=True), 'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'start': START}
    (OUT / 'index.json').write_text(json.dumps(idx, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (OUT / '_state.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')


# ---------- 전일 종가 ----------
class Closes:
    def __init__(self, codes):
        import numpy as np
        from common import load_panel
        p = load_panel()
        p = p[p['ticker'].isin(set(codes))][['ticker', 'date', 'close']]
        self.np = np
        self.d = {}
        for t, g in p.groupby('ticker'):
            g = g.sort_values('date')
            self.d[t] = (g['date'].values.astype('datetime64[D]'), g['close'].astype(float).values)

    def prev(self, code, day):
        a = self.d.get(code)
        if a is None:
            return None
        i = int(self.np.searchsorted(a[0], self.np.datetime64(day), side='left')) - 1
        if i < 0:
            return None
        v = a[1][i]
        return int(round(v)) if v == v and v > 0 else None


# ---------- 목록 ----------
def list_items(known, backfill_done, size):
    """최신 → 과거 순으로 목록을 읽어 START 이전이 나오면 멈춥니다. (이미 다 모은 뒤에는 전부 아는 쪽이 나오면 멈춤)"""
    out, seen = [], set()
    for page in range(1, 600):
        try:
            rows = get_json(LIST.format(p=page, n=size))
        except RuntimeError as e:
            if page == 1 and size != 20:
                log(f'리서치 목록 pageSize={size} 실패({e}) -> 20으로 다시 시도합니다.')
                return list_items(known, backfill_done, 20)
            if page == 1:
                raise
            log(f'리서치 목록 {page}쪽 실패: {e} (여기까지만 사용)')
            break
        if not isinstance(rows, list) or not rows:
            break
        new_in_page = 0
        stop = False
        for r in rows:
            d = str(r.get('writeDate', ''))
            i = r.get('researchId')
            if not i or not d:
                continue
            if d < START:
                stop = True
                continue
            if i in seen:
                continue
            seen.add(i)
            out.append(r)
            if i not in known:
                new_in_page += 1
        if stop or (backfill_done and new_in_page == 0):
            break
        time.sleep(0.15)
    return out


def main():
    minutes = float(opt('research', 'minutes', '20') or 20)
    deadline = time.time() + minutes * 60
    st, state = load_store()
    fails = state.get('fail', {})
    backfill_done = bool(state.get('done')) and state.get('start') == START   # 시작일이 바뀌면 다시 이어받기
    log(f'리서치 수집 시작: 저장된 리포트 {len(st)}건, 시간 제한 {minutes:.0f}분, 이어받기 {"끝남" if backfill_done else "진행 중"}')
    items = list_items(set(st), backfill_done, 100)
    if not items:
        log('리서치 목록이 비어 있습니다. 네이버 주소가 바뀌었을 수 있습니다. (이미 모은 내용은 그대로 둡니다)')
        return
    todo = [r for r in items if r['researchId'] not in st and fails.get(str(r['researchId']), 0) < 3]
    todo.sort(key=lambda r: (str(r['writeDate']), r['researchId']), reverse=True)
    log(f'목록 {len(items)}건 중 새로 받을 리포트 {len(todo)}건')
    if todo:
        cl = Closes({str(r.get('itemCode', '')).zfill(6) for r in todo})
    got = bad = consec = 0
    for k, r in enumerate(todo):
        if time.time() > deadline:
            log(f'시간 제한으로 여기서 멈춥니다. 남은 {len(todo) - k}건은 다음 실행에서 이어받습니다.')
            break
        i = r['researchId']
        try:
            j = get_json(DETAIL.format(i=i))
            c = j.get('researchContent') or {}
        except RuntimeError as e:
            fails[str(i)] = fails.get(str(i), 0) + 1
            bad += 1
            consec += 1
            if consec >= 8:
                log(f'리서치 상세가 계속 실패해서 멈춥니다: {e}')
                break
            continue
        consec = 0
        code = str(r.get('itemCode', '')).zfill(6)
        d = str(r['writeDate'])
        op = str(c.get('opinion') or '').strip()
        st[i] = [i, code, r.get('itemName', ''), r.get('brokerName', ''), d, r.get('title', ''), op, norm_opinion(op),
                 to_int(c.get('goalPrice')), cl.prev(code, d), summarize(c.get('content') or '')]
        got += 1
        if got % 300 == 0:
            save_store(st, {**state, 'fail': fails})
            log(f'  리서치 {got}건 받음…')
        time.sleep(0.2)
    # 게시 전일 종가를 일봉 자료(대시보드와 같은 값)로 전부 다시 맞춥니다. (받을 때 값이 잠정치였을 수 있음)
    try:
        cl2 = Closes({r[1] for r in st.values()})
        fixed = 0
        for r in st.values():
            v = cl2.prev(r[1], r[4])
            if v and v != r[9]:
                r[9] = v
                fixed += 1
        log(f'게시 전일 종가 다시 맞춤: {fixed}건 수정')
    except Exception as e:  # noqa: BLE001
        log(f'게시 전일 종가 다시 맞추기 실패: {e}')
    remain = [r for r in todo if r['researchId'] not in st and fails.get(str(r['researchId']), 0) < 3]
    state['done'] = not remain
    state['start'] = START
    state['fail'] = {k: v for k, v in fails.items() if int(k) not in st}
    save_store(st, state)
    log(f'리서치 수집 끝: 새로 {got}건, 실패 {bad}건, 남음 {len(remain)}건, 전체 {len(st)}건')


if __name__ == '__main__':
    main()
