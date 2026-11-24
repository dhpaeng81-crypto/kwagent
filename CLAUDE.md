# CLAUDE.md — kwagent 인수인계 (Claude Code 용)

## 사용자와 목표
- 사용자: 한국어 사용자이고 Python 개발자가 아님. 설명은 **한국어, 쉬운 말**로. 명령은 복사해서 붙여 넣을 수 있게 줄 것.
- 목표: 한국의 **1개월(주별 4주) 기상예측을 자체적으로 수행하는 에이전트**. 1개월 단위 정확도를 높이는 것이 핵심.
  + **2주 일별 예측**(2026-11-23 사용자 요청): 내일부터 14일, 매일 발표. 아래 '2주 일별 예측' 절.
- 예측 변수: **기온, 운량, 일사량, 강수(비/눈)**. (일사량은 2026-11-23 사용자 요청으로 추가)
- 영역: 1단계는 전국 1개 영역 → 최종 목표는 **중부권/남부권** 분리(코드에는 이미 구현, 설정으로 켬).
- 배포 방식(사용자 선택): **GitHub Actions 로 매주 자동 실행 + GitHub Pages 웹사이트**. 로컬 Python 설치는 원하지 않음.

## 현재 상태 (2026-11-17 기준)
- 전체 파이프라인을 구현함: 수집 → 학습 → 예측 → 결합 → 채점 → 보고서·해설 → 웹사이트.
- **합성 자료로만 시험함** (`pytest -q` 5개 통과, 약 70초). 만든 환경에 외부 네트워크가 없어서
  **실제 API(Open-Meteo, NOAA, BoM)로는 한 번도 실행하지 못했다.**
  → 첫 작업은 실제 자료원 점검이다(아래 P0).
- 사용자는 아직 GitHub 저장소를 만들지 않았을 수 있음. `SETUP_GITHUB.md` 가 사용자용 안내서.
- 관련 문서(claude.ai 아티팩트, 사용자 소유):
  - 설계서: https://claude.ai/artifact/8C2UqtAxBMhxAErZVpqbug
  - 배경 조사(KMA vs NOAA vs ECMWF 장기예보 비교): https://claude.ai/artifact/SsTyFJFtHe65BgbFHr4xMf

## 예측 정의 (기상청 1개월전망과 동일하게 맞춤)
- 매주 목요일 발표. 대상은 발표일이 속한 주의 **다음다음 주 월요일부터 4주**
  (예: 2026-10-22 발표 → 11/02~11/29). 구현은 `calendar.target_weeks`.
- 기온(주평균)·운량(주평균 %)·일사량(일합 MJ/m² 의 주평균)·강수량(주합 mm)은 1991~2020 평년 삼분위 기준
  낮음/비슷/높음 확률. 표시는 10% 단위, 합 100, 최소 5%.
- 강수형태: 일강수 ≥1 mm 를 강수일로 보고, 비가 아닌 비율이 0.5 이상이면 눈 오는 날.
  주별 비 오는 날·눈 오는 날 수와 눈 올 확률(눈 오는 날 ≥1일)을 낸다.
- 영역평균 = ASOS 주요 지점 21곳 좌표의 단순평균(`regions.py`). 권역은 **행정구역 기준**
  (안동=경북→남부).

## 구조
```
kwagent/
  cli.py          명령: train | run | forecast | verify | backtest | status | site | doctor
  agent.py        오케스트레이션 (Agent 클래스)
  calendar.py     발표일→목표 주, today_kst() (Actions 는 UTC 라 반드시 KST 날짜 사용)
  regions.py      지점·권역
  features.py     영역평균, 7일 집계, Climatology(평년 삼분위·일평년·눈 빈도)
  data/openmeteo.py  ERA5 archive(지점별 CSV 증분 캐시), EC46(seasonal API), GEFS(ensemble API)
  data/indices.py    Niño3.4(wksst9120.for), AO(CPC daily), MJO RMM(BoM) 파서
  data/provider.py   OpenMeteoProvider(실자료) / make_provider(offline→SyntheticProvider)
  data/synthetic.py  오프라인 시험용 가짜 날씨·앙상블
  models/statistical.py  다항 로지스틱(추세·14일 지속성·지수·계절), 연도 GroupKFold 로 C 선택
  models/dynamical.py    멤버 주간값→편향보정(기온·운량 차감, 강수 비율 0.3~3)→삼분위 계수
  models/combine.py      RPSS 가중 결합 + 기후값 수축 α + 10% 반올림
  store.py        SQLite: forecasts, ptype, verification, ptype_verification
  verify.py       RPS/RPSS/신뢰도/Brier
  narrative.py    LLM 해설(ANTHROPIC_API_KEY 있을 때, 없으면 규칙 기반)
  report.py       md 표 + matplotlib 확률 막대
  site.py         정적 웹사이트(site/): index, f/<날짜>, archive, verification
  doctor.py       실자료원 점검 (단기 앙상블 모델 포함)
  daily.py        2주 일별 예측: 단기 앙상블 혼합·편향보정·범위/확률·채점·보고서
.github/workflows/weekly.yml  목 07:10 KST: (모델 없으면 train) → run → site → 기록 커밋 → Pages 배포
.github/workflows/train.yml   분기별 재학습
.github/workflows/daily.yml   매일 06:40 KST: kwagent daily → site → 기록 커밋 → Pages 배포
```

## 정확도 개선 루프 (설계 핵심 — 바꿀 때 유지할 것)
1. 매 실행마다 `verify` 가 지난 예측(모든 source)을 ERA5 로 채점해 `verification` 에 저장.
2. 검증 ≥4건: `Store.bias()` 로 역학모델 편향 보정. ≥20건이면 같은 계절(±1개월)만 사용.
3. 검증 ≥8건: 예측원 가중치를 사전값(통계 0.35·EC46 0.45·GEFS 0.20, 미검증 역학모델 ×0.5)에서
   최근 52주 RPSS 비례로 전환.
4. `blend_raw`(수축 전) 검증 ≥20건: α 를 RPS 최소화 격자탐색으로 재추정.
5. 공개 API 는 '현재' 앙상블만 준다 → 과거 역학모델 예측으로 백테스트·사전보정 불가.
   그래서 역학모델 보정은 운영하면서 쌓인다. `forecasts.ens_mean_raw` 를 지우지 말 것.

## 데이터 의존성과 **검증 안 된 가정** (P0 에서 확인)
| 항목 | 현재 가정 | 확인 방법 |
|---|---|---|
| EC46 모델 id | `ecmwf_ec46` (seasonal-api.open-meteo.com/v1/seasonal) | `kwagent doctor` 의 daily keys |
| GEFS 모델 id | `ncep_gefs05` (ensemble-api, 35일, 31멤버) | 동일 |
| daily 변수명 | temperature_2m_mean, cloud_cover_mean, precipitation_sum, rain_sum, snowfall_sum | 동일. seasonal API 에 rain_sum 이 없으면 snowfall_sum 으로 추정(코드에 대비) |
| 멤버 키 | `<var>_memberNN`, 컨트롤은 접미사 없음(member 0) | `_MEMBER_RE` |
| 다지점 응답 | 쉼표로 묶은 좌표 → JSON 리스트 | `_get` 은 dict/list 모두 처리 |
| Niño3.4 | CPC wksst9120.for, 숫자 8개 중 6번째 = Niño3.4 편차 | doctor |
| AO | CPC norm.daily.ao...current.ascii `y m d ao` | doctor |
| MJO | BoM rmm.74toRealtime.txt `y m d rmm1 rmm2 ...` | doctor (BoM 이 http→https 또는 주소 변경 가능) |
| 사용 조건 | Open-Meteo 무료 = 비상업, 일 1만 호출 | GitHub 공유 IP 에서 429 가능 → 재시도/대기 늘리기 |

### P0 점검 결과 (2026-11-23, `kwagent doctor` 실자료)
- ERA5·EC46(`ecmwf_ec46`, 51멤버, 46일)·GEFS(`ncep_gefs05`, 31멤버, 35일): **정상**. daily 키 =
  5개 변수 × 멤버(컨트롤 무접미사 + `_member01..`) → 가정대로. seasonal API 에도 rain_sum 있음.
- Niño3.4: 정상(약 1~2주 지연). AO: 정상, 단 파일이 월 1회 갱신이라 최대 ~6주 지연.
- **MJO(BoM RMM): 파일이 2024-02-24 에서 갱신 중단**, 게다가 python-requests 를 403 으로 차단(curl 은 200).
  → `indices.predictors_at` 에 지수별 최대 자료 나이(`_PRED_SPEC`)를 추가해, 오래된 값은 0(기후값).
  (전에는 2년 묵은 RMM 값이 그대로 예측인자로 들어갔음.) 대체 MJO 출처(예: NOAA OMI) 찾기는 P1.

- **첫 Actions 실행 실패(429)**: Open-Meteo 무료판은 요청을 '지점 × 2주 = 1회'로 센다. 1991~ 한 지점 ≈ 940회라
  분당 600 초과, 21지점 ≈ 2만 회라 일 1만도 초과. → `fetch_archive` 를 1년 조각 + 조각마다 저장으로 바꾸고,
  시간·일 한도는 `QuotaError` 로 멈춤. ERA5 는 `data/era5/*.csv.gz` 로 **저장소에 커밋**(Actions 캐시는 실패 시 저장 안 되고 소멸 가능).
  `kwagent backfill` 이 GITHUB_OUTPUT 에 complete 를 남기고, weekly.yml 의 2시간 cron 이 다 받을 때까지 이어 받은 뒤
  학습·예측·배포. 모델이 생기면 2시간 cron 은 바로 끝남.

### 일사량 추가 (2026-11-23)
- Open-Meteo `shortwave_radiation_sum`(MJ/m²/일) → 내부 이름 `srad`. ERA5·EC46·GEFS 모두 제공(멤버 구조 동일) 확인.
- `features.VARS` 가 변수 목록의 기준. 표시(report/site/narrative)는 `report.result_vars` 로 예측에 실제 있는 변수만
  보여 줘 일사량 없는 옛 예측(2026-11-19)도 깨지지 않음.
- 통계모델 예측인자에 `a_srad`(14일 편차) 추가. 모델 파일에 `features` 목록을 저장 → 옛 모델도 로드 가능.
- ERA5 파일은 `openmeteo.REQUIRED_COLS`(temp, tmax, tmin, srad)가 모두 채워진 날까지만 '받은 것'으로 본다 →
  새 변수를 추가하면 옛 파일은 처음부터 다시 받는다. 변수를 또 추가할 때도 같은 방식.
- 역학모델 편향보정: 일사량은 기온·운량처럼 더하기 보정.
- 같은 재수집에 일 최고·최저기온(tmax, tmin)도 포함(2주 일별 예측용, 1개월 예측 변수는 아님).

### 운영 메모 (2026-11-24)
- ERA5 재수집(일사량·최고·최저) 21지점 완료, 통계모델 재학습(기온 CV-RPSS 0.03~0.04, 나머지 0 근처). 첫 2주 일별 예측 배포됨.
- 워크플로 교훈: (1) 대기하던 실행은 버튼 누른 시점 커밋으로 시작 → checkout `ref: main` 필수(아니면 store·era5 바이너리 충돌).
  (2) 같은 작업에서 upload-pages-artifact 직후 deploy-pages 하면 'artifact 0개'로 실패 → 배포는 별도 `deploy` 작업(environment github-pages).

## 2주 일별 예측 (`kwagent daily`, 2026-11-23 1단계)
- 변수: 평균·최고·최저기온, 운량(+하늘상태 확률: 맑음 <55%, 구름많음 55~85%, 흐림 ≥85%), 일사량, 강수량,
  강수확률, 눈 확률. 출력은 날짜별 10/50/90% 범위와 1991~2020 일평년(31일 평활).
- 강수확률·눈 확률은 **'평균적인 지점' 기준** = 비(눈) 온 지점 비율의 기대값 (`region_daily` 의 wet/snowd).
  영역평균 강수량 ≥1 mm 로 정하면 한 곳만 와도 '비'가 돼서 평년 확률이 90% 넘게 나왔음.
- 모델(config `daily.models`, Open-Meteo ensemble API) — **2026-11-24 실자료 확인**:
  ecmwf_ifs025(51멤버, ~14일), ecmwf_aifs025(51, ~14일), ncep_gefs_seamless(31, 30일+), icon_seamless(40, 7일).
  모든 모델이 temp·tmax·tmin·cloud·srad·precip·rain 제공. `ncep_gefs025` 는 9일까지만 값이 있어 seamless 로 바꿈.
  모델 예측이 끝나는 마지막 날은 부분 집계라 최고·최저가 치우쳐서 버림(`forecast` 의 areas). 가중치는 사전값.
- 개선 루프: 매일 `daily_verification` 에 채점 → 같은 모델·변수·예보일(±1일) 최근 60건 중 10건 이상이면
  편향 보정(기온·운량·일사량 차감, 강수 비율 0.5~2). 표 `daily_forecasts.mean_raw` 를 지우지 말 것.
- 저장소 표 `daily_forecasts`, `daily_verification` 은 CREATE IF NOT EXISTS 로 추가(기존 DB 자동 이행).
- 웹사이트: daily.html(최신), 정확도 탭 아래 일별 성적(1~3/4~7/8~14일: 평균오차, 평년 대비 개선, 범위 적중률, 강수확률 Brier).
- 2단계(예정): Open-Meteo Historical Forecast/Previous Runs API 로 과거 예측 받아 첫날부터 보정, EMOS 퍼짐 보정,
  성적 기반 가중치. 3단계: 도시별(21지점), 기상청 GDAPS(결정론) 추가 검토.

## 할 일 (우선순위)
**P0 — 첫 실운영**
1. 사용자와 함께 GitHub 저장소 생성·푸시, Pages(Source=GitHub Actions) 켜기, `weekly-forecast` 수동 실행.
   (`gh` CLI 가 있으면 `gh repo create kwagent --public --source . --push` 후 Pages 설정 안내.)
2. `kwagent doctor` 결과로 위 표의 가정을 확인하고 어긋나면 `config.yaml`/파서 수정.
3. `kwagent train` 실자료 결과(`reports/train_report.csv`)를 사용자에게 쉬운 말로 설명.
   통계모델 CV-RPSS 가 0 근처면 정상(1개월 예측은 어렵다). 음수면 C_GRID·예측인자 점검.
4. 첫 실제 웹사이트 화면을 확인(표·그래프·한글 글꼴·해설).

**P1 — 정확도**
5. 역학모델 **원자료 보존**: 현재 EC46/GEFS 원본은 `data/cache`(Actions 캐시, 소멸 가능)에만 있다.
   영역평균 멤버 주간값을 store 에 테이블로 저장해 나중에 재보정 가능하게.
6. EC46 **모델 기후값 대비 주간 편차**(Open-Meteo seasonal API weekly anomaly — ECMWF 과거예측 기반)를
   써서 검증 기록 없이도 첫 주부터 편향 없는 확률 산출 → `dynamical.py` 에 대안 경로 추가.
7. **기상청 대비 벤치마크**: 기상청 1개월전망 PDF
   (`https://www.weather.go.kr/w/repositary/xml/fct/mon/fct_mon1_108_YYYYMMDD.pdf`, 108=전국 추정 — 확인 필요)
   의 주별 확률을 수집해 같은 정답으로 RPSS 비교, 웹사이트 정확도 탭에 표시.
8. 신뢰도 도표(`verify.reliability`)를 정확도 탭에 추가.

**P2 — 확장**
9. 기상청 API허브 키 확보 시 ASOS 관측으로 정답 교체(운량 단위 '할' 주의, `regions.Point.stn` 사용).
10. 2단계(중부/남부): `regions_active: [korea, central, south]` + train. 권역당 지점 15~20곳으로 늘리기.
11. C3S 과거예측(CDS 키) 기반 ELR 보정, 해빙·눈덮임·성층권 예측인자.

## 작업 규칙
- 변경 후 `pytest -q` 통과 유지(오프라인). 실자료 기능은 `--offline` 경로가 깨지지 않게.
- `store.py` 스키마를 바꾸면 기존 `data/store.sqlite` 마이그레이션을 같이 작성(운영 기록이 곧 자산).
- 날짜는 `today_kst()` 사용. `date.today()` 금지(Actions=UTC).
- 출력 문구·웹사이트는 한국어. 확률 표기는 기상청 관례(낮음/비슷/높음, 적음/비슷/많음).
- `data/cache/`, `site/` 는 커밋하지 않음. `data/era5/`, `data/store.sqlite`, `data/models/`, `reports/` 는 워크플로가 커밋.

## 자주 쓰는 명령
```bash
pip install -e ".[llm,dev]"
pytest -q                                   # 오프라인 전체 시험
kwagent doctor                              # 실자료원 점검
kwagent train && kwagent run && kwagent site
python -m kwagent.cli backtest --offline --start 2024-10-03 --end 2025-03-27   # 합성 백테스트
```
