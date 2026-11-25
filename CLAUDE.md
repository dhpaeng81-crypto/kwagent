# CLAUDE.md — kwagent 인수인계 (Claude Code 용)

## 사용자와 목표
- 사용자: 한국어 사용자이고 Python 개발자가 아님. 설명은 **한국어, 쉬운 말**로. 명령은 복사해서 붙여 넣을 수 있게 줄 것.
- 목표: 한국의 **1개월(주별 4주) 기상예측을 자체적으로 수행하는 에이전트**. 1개월 단위 정확도를 높이는 것이 핵심.
  + **일별 예측**(2026-11-23 2주 → 2026-11-24 4주로 확장, 사용자 승인): 내일부터 28일, 매일 발표.
    1~14일은 날짜별 값, 15~28일은 '경향'(5일 평균의 평년 삼분위 확률). 아래 '2주 일별 예측' 절.
- 예측 변수: **기온, 운량, 일사량, 강수(비/눈)**. (일사량은 2026-11-23 사용자 요청으로 추가)
- 영역(2026-11-24 사용자 결정): **전국 + 중부(서울·인천·경기·강원·충청)·호남·경상**. 제주는 전국 평균에만.
  지점은 꼭 필요한 곳만 추가(호남 군산·정읍·남원, 경상 창원·구미) → 26지점(중부 10·호남 7·경상 8·제주 1).
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
- 영역평균 = ASOS 주요 지점 26곳 좌표의 단순평균(`regions.py`). 권역은 **행정구역 기준**
  (안동=경북→경상). 권역 키: korea·central·honam·yeongnam (옛 south=호남+경상+제주 는 지난 기록 표시용).

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
  report.py       md 표 + matplotlib 확률 막대(noscript·보고서용) + to_excel(1개월 → site/forecast_<발표일>.xlsx)
  (site.py 새로고침) 머리의 '새로고침' 버튼(.rf, REFRESH_JS): version.json 의 built 와 화면 meta kw-built 비교 → 다르면 ?r= 붙여 다시 불러옴.
                  화면을 다시 열 때도 확인해 알림. 홈 화면 앱엔 브라우저 새로고침이 없어서 추가(2026-11-25). 꼬리말에 관리자용 '예측 다시 돌리기' 링크.
  rights.py       저작권·AI 수집 거부(2026-11-24 사용자 요청): 꼬리말·이용약관(terms.html)·noai/TDM 메타·엑셀 '저작권' 시트·
                  그래프 워터마크, 도메인 맨 앞용 robots.txt/ai.txt/.well-known/tdmrep.json(site_root/). 권리자 표기 dhpaeng81-crypto
  methods.py      화면 맨 아래 '예측 방법'(눌러서 펼치는 항목, 화면별 daily·month·verify). **방법을 바꾸면 이 글도 같이 고칠 것**
  ui.py           화면 부품: 날씨 그림(SVG), 2주 '한눈에' 문장(daily_headlines), 1개월 경향 낱말·색깔표(month_chips/month_cell)
  site.py         정적 웹사이트(site/): index(=2주 일별, 기본), daily(같은 내용·옛 주소), month(1개월), f/<날짜>, archive, verification
                  엑셀: daily_<발표일>.xlsx, forecast_<발표일>.xlsx, verification.xlsx(요약 + 채점 기록, 일별은 최근 120일)
  static/         홈 화면 아이콘(icon.svg 원본 → PNG 들, mkicons.js 로 다시 렌더), chart.umd.min.js(Chart.js 4.4.4, npm 에서 복사),
                  daily.js(일별 대화형 그래프: <script id=ddata> JSON), month.js(1개월 확률 막대·강수형태: <script id=mdata>)
                  verify.js(정확도: 1개월 주차별 RPSS 선, 일별 평년 대비 개선 막대·모델별 오차(변수 선택): <script id=vdata>)
  doctor.py       실자료원 점검 (단기 앙상블 모델 포함)
  daily.py        2주 일별 예측: 단기 앙상블 혼합·편향보정·범위/확률·채점·보고서
.github/workflows/weekly.yml  목 07:10 KST: (모델 없으면 train) → run → site → 기록 커밋 → Pages 배포
.github/workflows/train.yml   분기별 재학습
.github/workflows/daily.yml   매일 06:40 KST: kwagent daily → site → 기록 커밋 → Pages 배포
```

## 저장소·게시 구조 (2026-11-24: 비공개 전환을 준비했으나 사용자가 '코드 공개 유지'로 결정 — 아래는 나중을 위한 준비물)
- 현재: 저장소 `kwagent` 공개, 이 저장소 Pages 로 배포. 보호는 권리 표시·이용약관·noai/TDM 메타·엑셀 저작권 시트·워터마크·LICENSE.
- 도메인 맨 앞 robots.txt 는 `dhpaeng81-crypto.github.io` 저장소가 있어야 적용됨(지금은 없음 → 페이지 meta 만 작동).
- 목표 구조: 코드 저장소 `kwagent-src`(비공개) → Actions 가 `deploy/publish_site.sh` 로 site/ 를 공개 저장소 `kwagent`
  (https://dhpaeng81-crypto.github.io/kwagent/ 유지)에, site_root/ 를 `dhpaeng81-crypto.github.io`(robots.txt 등)에 푸시.
- 비밀값 `SITE_TOKEN`(두 공개 저장소 Contents 쓰기, fine-grained)이 있으면 이 방식, 없으면 예전처럼 이 저장소 Pages 배포.
  사용자 작업(저장소 이름 변경·비공개 전환·공개 저장소 2개 생성·토큰 등록·Pages 설정)은 SETUP_PRIVATE.md.
- 비공개 저장소의 Actions 무료 한도는 월 2,000분. 매일 ~10분 + 매주 ~15분 ≈ 월 400분이라 여유. 2시간 cron 은 뺐다.
- LICENSE: All rights reserved(코드·결과물), 원자료 권리는 각 기관.

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
- (2026-11-26) GitHub 예약 실행이 몇 시간 늦거나 빠짐(11-25 일별 7시간 지연, 11-26 주간 미실행) → 예비 cron 추가:
  daily 08:17·10:43 KST, weekly 목 08:47·12:13 KST. 예약 실행은 오늘(이번 주) 결과가 이미 있으면 건너뜀(daily 는 check 작업).
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
- 웹사이트: index.html = 2주 일별(2026-11-24 사용자 요청으로 기본 화면), 1개월은 month.html. 모바일 홈 화면 추가용 manifest·아이콘 포함.
  **디자인 원칙(2026-11-24 사용자 승인)**: 빽빽하지 않게 — 맨 위에 결론(한눈에 요약), 그래프는 버튼으로 골라 보기(_seg_card),
  표·설명·해설은 접기(_fold, details.about). 내용은 줄이지 않고 '먼저 보이는 것'과 '눌러서 보는 것'을 나눈다.
  일별 화면은 변수별 카드 4개(기온·강수·운량·일사량) 대화형 그래프(마우스 올리면 수치) + 표 + '엑셀로 받기'
  (site 빌드 때 `daily.to_excel` 로 daily_<발표일>.xlsx 생성, openpyxl). matplotlib PNG 는 noscript·보고서용으로 유지.
  정확도 탭 아래 일별 성적(1~3/4~7/8~14일: 평균오차, 평년 대비 개선, 범위 적중률, 강수확률 Brier).
- **4주 확장(2026-11-24)**: config `daily.days: 28`, `trend_from: 15`, `trend_window: 5`. 15일 이후 모델 = EC46(`ecmwf_ec46`,
  seasonal API, `from_lead: 14`, 매일 00UTC 실행·약 21시간 뒤 공개) + GEFS 35일(`ncep_gefs_seamless` days 31).
  ECMWF 15일 예측은 13일째에 끝나서 EC46 을 14일부터 넣음. `daily.trend_normals`(연중일별 5일 평균 삼분위, 앞뒤 15일),
  `_trend` → day['trend'][var] = {p:[낮음,비슷,높음], lo, hi, cal}. 화면은 '3~4주 뒤 경향' 달력(가장 큰 쪽 <45% 면 '불확실').
- **장기 모델 비 치우침(2026-11-24 확인)**: 12월 중순 EC46·GEFS 영역평균 일강수 ≈2.1 mm vs ERA5 12월 평년 0.93 mm(약 2배),
  운량도 +10~15%p. → 보정 전에는 강수·운량 경향/1개월 전망이 '많음'으로 치우침. 대책: `daily.proxy_bias`(같은 모델 12~16일째
  채점 치우침)를 15일 이후 일별·1개월 전망(`agent._forecast_region`, 결과 regions[r]['bias'] = own|proxy)에 임시 적용.
  보정 전이면 화면에 노란 '보정 전' 안내. 채점이 쌓이면 자동으로 그 예보일 자신의 채점으로 넘어감.
  근본 대책은 P1-6(EC46 모델 기후값 대비 편차).
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
7. **(구현 2026-11-24) 기상청 대비 벤치마크** — `kma.py`·`kma.yml`(목 12:10 KST, 금 예비): 전국 PDF(108)의 '주·지역별 평균기온/강수량 확률 전망' 표를 pdftotext 로 읽어 forecasts 에 source='kma' 로 저장 → 기존 verify 가 같은 정답으로 채점,
   정확도 화면에 '기상청 대비' 타일·선. 지난 발표분은 사이트에서 사라짐(당일 받기 필수). 권역 비중은 우리 지점 수. 지역 코드: 109 서울경기·101 영서·105 영동·
   133 충남·131 충북·146 전북·156 전남·143 경북·159 경남·184 제주(지역별 PDF도 있음). 원래 메모: 기상청 1개월전망 PDF
   (`https://www.weather.go.kr/w/repositary/xml/fct/mon/fct_mon1_108_YYYYMMDD.pdf`, 108=전국 추정 — 확인 필요)
   의 주별 확률을 수집해 같은 정답으로 RPSS 비교, 웹사이트 정확도 탭에 표시.
8. 신뢰도 도표(`verify.reliability`)를 정확도 탭에 추가.

**P2 — 확장**
9. 기상청 API허브 키 확보 시 ASOS 관측으로 정답 교체(운량 단위 '할' 주의, `regions.Point.stn` 사용).
10. (완료 2026-11-24) 권역: 전국·중부·호남·경상. 웹사이트는 권역 버튼(.rtabs, 고른 권역을 브라우저에 기억)으로 전환.
    더 늘릴 때: 강원 영동(대관령·속초), 호남 남해안(고흥·완도), 경상 북부(영주·울진) 후보.
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
