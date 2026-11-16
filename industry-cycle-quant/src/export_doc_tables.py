"""원본 Word 문서의 표를 CSV/JSON/XLSX 로 변환 (1회성)."""
import json, sys
from pathlib import Path
import docx
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

src, root = Path(sys.argv[1]), Path(sys.argv[2])
t = docx.Document(src).tables
names = ["산업 사이클 참고", "산업별 핵심 지표", "점수 구성", "점수 구간", "대시보드 화면", "기존 데이터"]
data = [[[c.text for c in r.cells] for r in tb.rows] for tb in t]

cy = [dict(industry=r[0], cycle=r[1].replace("\n", " / "), phases=r[2], drivers=r[3], caution=r[4]) for r in data[0][1:]]
(root / "docs/data").mkdir(parents=True, exist_ok=True)
(root / "docs/data/cycles.json").write_text(json.dumps(cy, ensure_ascii=False, indent=1), encoding="utf-8")

wb = Workbook(); wb.remove(wb.active)
thin = Side(style="thin", color="D0D5DD")
for nm, rows in zip(names, data):
    ws = wb.create_sheet(nm)
    for r in rows: ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for i, col in enumerate(zip(*rows), 1):
        w = max(max(len(x) for x in str(v).split("\n")) for v in col)
        ws.column_dimensions[get_column_letter(i)].width = min(max(w * 1.7 + 2, 10), 48)
    ws.freeze_panes = "A2"
wb["산업 사이클 참고"].sheet_properties.tab_color = "1F5EFF"
n = wb.create_sheet("메모")
n.append(["주의"]); n.append(["국면별 최솟값·최댓값을 단순 합산해 주기 길이를 계산하면 안 됩니다. 산업별 통일 평균이 없는 경우 경험적 분석 범위입니다."])
n.append(["출처: 산업 사이클 기반 퀀트 투자와 대시보드 설계 (작성 기준일 2026-11-16)"]); n.column_dimensions["A"].width = 110
wb.save(root / "industry_cycle_tables.xlsx")
print("ok", len(cy))
