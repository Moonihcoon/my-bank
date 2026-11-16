# 산업 사이클 퀀트 대시보드

산업 사이클 점수와 종목 점수를 합산해 후보를 보여주는 **의사결정 보조 화면**입니다. 주문은 자동 실행하지 않습니다.

> 현재 `docs/data/dashboard.json` 은 **가상 샘플 데이터**입니다(화면 상단에 경고 표시). 실제 데이터를 연결하면 `is_demo` 가 꺼지고 경고가 사라집니다.

## 구성
| 경로 | 내용 |
|---|---|
| `docs/index.html` | 대시보드 (시장 요약·산업 사이클·종목 후보·성과 검증·데이터 관리·사이클 참고) |
| `src/collect_kiwoom.py` | 키움 REST API 일봉(ka10081) 수집, 연속조회·호출 간격·재시도·잘림 감지 |
| `src/build_scores.py` | 산업 35 / 실적 25 / 추세 20 / 밸류 10 / 위험 10 점수 → `docs/data/dashboard.json` |
| `src/make_demo.py` | 화면 확인용 가상 데이터 생성 (`data/demo/`) |
| `data/industry_map.csv` | 종목 → 산업 분류표 (**초안, 직접 확인·확장 필요**) |
| `data/industry_signals.csv` | 산업 지표 입력(국면·재고·가격·수주·공급, -1~+1). 빈 칸은 "미확인"으로 낮은 신뢰도 처리 |
| `data/fundamentals.csv` | DART 등에서 만든 종목 재무 입력 |
| `industry_cycle_tables.xlsx` | 원본 문서의 표 6개 |
| `.github/workflows/daily.yml` | 평일 장 마감 후 수집→점수→저장 |

## 실행
```bash
pip install pandas numpy requests
python src/make_demo.py && python src/build_scores.py --root data/demo --demo   # 샘플
cd docs && python -m http.server 8000                                           # http://localhost:8000
# 실제 데이터
export KIWOOM_APPKEY=... KIWOOM_SECRETKEY=...    # 채팅·코드·저장소에 넣지 마세요
python src/collect_kiwoom.py && python src/build_scores.py
```
GitHub Actions 사용 시 저장소 Settings → Secrets and variables → Actions 에 `KIWOOM_APPKEY`, `KIWOOM_SECRETKEY` 를 등록합니다.

## 공개 범위 주의
GitHub Pages 로 게시한 사이트는 저장소가 비공개여도 **URL을 아는 누구나 볼 수 있습니다**(Enterprise 접근 제어 제외). 실제 후보·점수는 공개 게시하지 않는 것을 권장하며, 로컬 실행 또는 비공개 호스팅을 쓰세요.

## 추가된 모듈
`collect_dart.py`(재무), `collect_signals.py`(산업 지표→신호·국면), `build_industry_map.py`(분류표 확장), `backtest.py`(워크포워드). 출처·순서는 [docs/data_sources.md](docs/data_sources.md). 합성 데이터로 동작만 확인했고 실제 API 호출은 이 세션에서 하지 못했습니다.

## 아직 안 된 것 (확정 전 필수)
1. 산업 지표·재무 CSV를 채우는 수집기 (OpenDART, 공개 산업 통계) — 지금은 수동 입력
2. 상장폐지 종목 포함 + 거래비용·세금·슬리피지 반영 워크포워드 백테스트 → 점수 구간 확정
3. 산업 분류표 전체 종목 확장 (3,408종목 일일 수집은 호출 한도상 배치·재시도 설계 필요)
4. `docs/data/backtest.json` (`{"summary":{"CAGR":"..","MDD":".."},"note":"..."}`) 생성 시 '성과 검증' 화면에 표시

## 점수 구간(초안)
80~100 우선 검토 후보(추세·유동성·위험 필터 전부 통과 필요, 미통과 시 한 단계 강등) / 70~79 매수 후보 관찰 / 55~69 관찰 / 55 미만 제외·보류.

## 기존 일봉 데이터 연결
```bash
python src/import_local_stock.py --src "C:\Users\...\Desktop\stock\export" --out ../stockdata
python src/build_industry_map.py --data ../stockdata --keep-unclassified
python src/build_scores.py --root ../stockdata --out ../stockdata/dashboard.json
python src/backtest.py --root ../stockdata --split 2024-01-01 --min-score 58 --top-n 20 --no-data-filter
```
실제 시세·점수 파일은 저장소에 올리지 않습니다(`../stockdata` 는 저장소 밖).
