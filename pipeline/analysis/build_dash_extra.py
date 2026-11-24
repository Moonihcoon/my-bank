"""급등주 대시보드(index.html)에도 '상승률 200' 과 같은 탭(시장 지도·리서치·지수차트)을 더합니다.
같은 data/·px/ 를 읽기 때문에 한 번 업데이트하면 두 대시보드가 같은 데이터로 갱신됩니다.
build_dash 가 만든 web/index.html 을 그대로 고쳐 쓰므로 build_dash 뒤에 실행합니다."""
import re

p = 'web/index.html'
page = open(p, encoding='utf-8').read()
OLD = "['stats','list','stocks','screen','cand','calendar','reasons']"
NEW = "['stats','list','stocks','screen','cand','calendar','reasons','map','research','ix']"
HOOK = "if(name==='map')await tabMap();if(name==='research')await tabRs();if(name==='ix')await tabIx();"
# 이전에 더한 부분을 먼저 걷어 내서, 여러 번 실행해도(화면 템플릿이 바뀐 뒤에도) 같은 결과가 되게 합니다.
page = re.sub(r'<!--XTAB-->.*?<!--/XTAB-->', '', page, flags=re.S)
page = page.replace(NEW, OLD).replace(HOOK, '')
if True:
    MAP = open('web/tpl_map.html', encoding='utf-8').read()
    MAPJS = open('web/tpl_map.js', encoding='utf-8').read()
    RS = open('web/tpl_rs.html', encoding='utf-8').read()
    RSJS = open('web/tpl_rs.js', encoding='utf-8').read()
    IX = open('web/tpl_ix.html', encoding='utf-8').read()
    IXJS = open('web/tpl_ix.js', encoding='utf-8').read()

    # 1) 탭 버튼
    m = re.search(r'(<button role="tab" data-tab="reasons"[^>]*>.*?</button>)', page, flags=re.S)
    assert m, 'reasons 탭 버튼을 찾지 못함'
    btn = ('\n<button role="tab" data-tab="map" aria-selected="false">시장 지도</button>'
           '\n<button role="tab" data-tab="research" aria-selected="false">리서치</button>'
           '\n<button role="tab" data-tab="ix" aria-selected="false">지수차트</button>')
    page = page.replace(m.group(1), m.group(1) + '<!--XTAB-->' + btn + '<!--/XTAB-->', 1)

    # 2) 화면 영역(기존 첫 영역 앞에 끼워 넣음)
    k = page.index('<section id="p-stats"')
    page = page[:k] + '<!--XTAB-->' + MAP + RS + IX + '<!--/XTAB-->' + page[k:]

    # 3) 탭 목록·탭 열 때 불러오기
    old_list = "['stats','list','stocks','screen','cand','calendar','reasons']"
    assert page.count(old_list) == 2, page.count(old_list)
    page = page.replace(old_list, "['stats','list','stocks','screen','cand','calendar','reasons','map','research','ix']")
    anchor = "if(name==='reasons')await tab5();"
    assert page.count(anchor) == 1
    page = page.replace(anchor, anchor + "if(name==='map')await tabMap();if(name==='research')await tabRs();if(name==='ix')await tabIx();")

    # 4) 스크립트
    page += '<!--XTAB--><script>' + MAPJS + '</script><script>' + RSJS + '</script><script>' + IXJS + '</script><!--/XTAB-->'
    open(p, 'w', encoding='utf-8').write(page)
    print('급등주 대시보드에 탭 3개 추가', len(page))
