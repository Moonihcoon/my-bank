"""키움 업종(지수) 차트 조회 점검 - 코스피(001)·코스닥(101) 일봉/분봉/주봉/월봉이 되는지, 얼마나 과거까지 오는지 확인합니다."""
import sys, json, time
from pathlib import Path
PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE)]
from common import kiwoom_keys
from kiwoom_api import Kiwoom

api = Kiwoom(*kiwoom_keys())
today = time.strftime('%Y%m%d')


def first_list(j):
    for k, v in j.items():
        if isinstance(v, list):
            return k, v
    return None, []


def run(title, api_id, body, datekey_candidates, max_pages=12):
    print(f'\n===== {title} {api_id} {body}')
    cont = nkey = None
    n = 0
    allrecs = []
    key = None
    try:
        for p in range(max_pages):
            j, cont, nkey = api.call(api_id, '/api/dostk/chart', body, cont, nkey)
            if p == 0:
                print('응답 최상위 키:', list(j.keys()))
            key, recs = first_list(j)
            if not recs:
                print('목록이 비어 있음', str(j)[:300])
                break
            allrecs.extend(recs)
            if cont != 'Y':
                break
    except Exception as e:
        print('오류:', e)
        return
    print('목록 키:', key, ' 받은 건수:', len(allrecs), ' 연속조회:', cont)
    if allrecs:
        print('첫 항목  :', json.dumps(allrecs[0], ensure_ascii=False))
        print('둘째 항목:', json.dumps(allrecs[1], ensure_ascii=False) if len(allrecs) > 1 else '-')
        print('마지막   :', json.dumps(allrecs[-1], ensure_ascii=False))


for code, nm in (('001', '코스피'), ('101', '코스닥')):
    run(f'{nm} 일봉', 'ka20006', {'inds_cd': code, 'base_dt': today}, ('dt',), 12)
run('코스피 일봉(날짜 없이)', 'ka20006', {'inds_cd': '001'}, ('dt',), 2)
run('코스피 분봉 1분', 'ka20005', {'inds_cd': '001', 'tic_scope': '1'}, ('cntr_tm',), 40)
run('코스닥 분봉 1분', 'ka20005', {'inds_cd': '101', 'tic_scope': '1'}, ('cntr_tm',), 3)
run('코스피 주봉', 'ka20007', {'inds_cd': '001', 'base_dt': today}, ('dt',), 2)
run('코스피 월봉', 'ka20008', {'inds_cd': '001', 'base_dt': today}, ('dt',), 2)
run('코스피 월봉(대체 ID)', 'ka20019', {'inds_cd': '001', 'base_dt': today}, ('dt',), 2)
print('\n끝')
