# 미구현 항목 보완 가이드 (데이터 출처와 방법)

| 부족한 것 | 어디서 | 무료/유료 | 이 저장소의 처리 |
|---|---|---|---|
| 종목 재무(영업이익률·부채비율·FCF) | OpenDART `fnlttSinglAcnt`, `fnlttSinglAcntAll` | 무료(키당 일 약 20,000건) | `src/collect_dart.py` — 접수일(avail)로 시점 보존, 캐시 이어받기 |
| 실적 추정치(est_revision) | FnGuide·에프앤가이드 컨센서스 등 | **유료** | 비워 두면 '미확인'(신뢰도↓). 구독 시 `fundamentals.csv` 의 est_revision 열에 채움 |
| 정상화 PER | KRX Data Marketplace 시가총액 + DART 3개년 순이익 | 무료(내려받기) | `data/krx_marketcap.csv`(code,market_cap) 두면 최신 행에만 계산 |
| 산업 가격·재고(반도체) | 한국은행 ECOS, 통계청 KOSIS 오픈API, 관세청/산업부 수출입 통계 | 무료(키 발급) | `collect_signals.py` 의 ecos/kosis 제공자. 통계코드·표ID는 각 사이트 검색에서 확인해 `signal_sources.csv` 에 입력 |
| DRAM·NAND 고정거래가 | TrendForce/DRAMeXchange 월 발표, 기업 실적발표 자료 | 상세 **유료**, 요약 공개 | `data/manual/*.csv`(date,value) 수동 기록 → csv 제공자 |
| 조선 수주·선가 | 클락슨(유료), 업계 공표치·언론 | 상세 **유료** | 수동 CSV |
| 해저케이블 확정 발주·FID | ENTSO-E·IEA 보고서, 기업 공시·IR | 무료(수작업) | 수동 CSV |
| 구리 등 원자재 | FRED(PCOPPUSDM 등) | 무료(키 발급) | fred 제공자 (기본 비활성) |
| 종목→산업 분류 | KRX 상장종목 CSV + 사업보고서 매출구성 | 무료 | `build_industry_map.py` (규칙 + 확정 overrides, 미분류 별도) |
| 상장폐지 종목 | KRX 상장폐지 현황, 키움 종목조회(과거 종목은 한계) | 무료/부분 | 상폐 종목 시세 파일을 `data/prices/` 에 포함해야 생존편향 감소 — **자동화 미완** |
| 과거 시점별 종목 정보 | 위 자료의 as_of/avail 이력 | - | `score_at(asof)` 가 시점 이전 자료만 사용 |
| 백테스트 | 위 자료 전부 | - | `src/backtest.py` — 신호 다음 거래일 체결, 비용·상폐 가정, 표본 내/외 분리 |

## 순서 (권장)
1. 키움 키로 `collect_kiwoom.py` 실행 → 최소 2020년부터의 일봉 적재 (수정주가 주의).
2. KRX에서 상장종목·시가총액 CSV 내려받아 `build_industry_map.py` → 미분류 종목을 `industry_overrides.csv` 로 확정.
3. `collect_dart.py` (여러 날에 나눠 실행) → `fundamentals.csv`.
4. `signal_sources.csv` 에서 확보 가능한 지표부터 `enabled=1` → `collect_signals.py`.
5. 상장폐지 시세 확보 후 `backtest.py --split YYYY-MM-DD` — 표본 내에서만 조정하고 표본 외는 한 번만 확인.
6. 결과가 기준지수 대비 의미 있고 비용 가정을 현실 값으로 바꿔도 유지될 때만 점수 구간을 확정.

## 아직 사람이 해야 하는 것
- 실제 API 키 발급·등록, 통계코드 확인, DRAM·조선 등 유료/비정형 지표 기록
- 현행 증권거래세율·수수료 확인 후 `--sell-tax`, `--commission` 조정
- 상장폐지 종목 시세 확보 (이 세션에서는 외부 사이트 접근 불가로 자동화·검증하지 못함)
