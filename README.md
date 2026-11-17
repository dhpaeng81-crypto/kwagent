# kwagent — 한국 1개월 기상예측 에이전트

매주 목요일, **발표 다음다음 주 월요일부터 4주간**의 주별 기온·운량·강수량을
"낮음/비슷/높음" 삼분위 확률로 예측하고, 비·눈 강수형태와 LLM 해설을 붙여 보고서를 만듭니다.
형식은 기상청 1개월전망과 같습니다(10% 단위 확률, 1991~2020 평년 기준).

> **Python 설치 없이 쓰려면** → [SETUP_GITHUB.md](SETUP_GITHUB.md): GitHub Actions 가 매주 자동 실행하고
> GitHub Pages 웹사이트로 결과를 보여줍니다. Claude Code 로 이어서 개발할 때는 [CLAUDE.md](CLAUDE.md) 를 먼저 읽습니다.

## 빠른 시작 (로컬 Python)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[llm,dev]"

pytest -q                         # 합성 자료로 전체 흐름 시험 (네트워크 불필요, 약 1분)

kwagent train                     # 1991~ ERA5 수집 + 통계모델 학습 (최초 1회, 수십 분)
kwagent run                       # 지난 예측 검증 → 이번 주 예측 → reports/ 에 md·json·png
kwagent status                    # 예측원별 RPSS 성적표
kwagent site                      # site/ 에 웹사이트 생성 (index.html 을 브라우저로 열기)
kwagent doctor                    # 실제 자료원 연결·형식 점검
```

`ANTHROPIC_API_KEY` 환경변수가 있으면 Claude 가 해설을 쓰고, 없으면 규칙 기반 요약을 씁니다.

## 데이터 (모두 API 키 불필요)

| 용도 | 자료 | 경로 |
|---|---|---|
| 정답·학습 | ERA5 재분석 일자료 (기온·운량·강수·비) | Open-Meteo Historical API |
| 역학모델 | ECMWF EC46 (46일, 51멤버) | Open-Meteo Seasonal API |
| 역학모델 | NOAA GEFS 0.5° (35일, 31멤버) | Open-Meteo Ensemble API |
| 예측인자 | Niño3.4(주간), AO(일), MJO RMM(일) | NOAA CPC, 호주 BoM 텍스트 파일 |

Open-Meteo 는 비상업 용도 무료입니다. 상업적으로 쓰려면 유료 API 키가 필요합니다.
모델 식별자(`ecmwf_ec46`, `ncep_gefs05`)는 `config.yaml` 에서 바꿀 수 있습니다. 처음 실행할 때 로그에서 멤버 수를 확인하세요.

## 구조

```
kwagent/
  calendar.py        발표일 → 목표 4주
  regions.py         21개 ASOS 대표 지점, 중부/남부 구분
  data/openmeteo.py  ERA5·EC46·GEFS 수집 + 캐시
  data/indices.py    Niño3.4·AO·MJO
  data/synthetic.py  오프라인 시험용 합성 자료
  features.py        영역평균, 주간집계, 평년 삼분위, 강수형태 분류
  models/statistical.py  다항 로지스틱 회귀 (추세·지속성·기후지수)
  models/dynamical.py    앙상블 → 편향보정 → 확률
  models/combine.py      RPSS 가중 결합 + 기후값 수축 + 10% 반올림
  store.py           SQLite 예측·검증 기록 (편향·가중치 학습의 근거)
  verify.py          RPS, RPSS, 신뢰도
  narrative.py       LLM 해설
  site.py            정적 웹사이트 (GitHub Pages)
  doctor.py          자료원 점검
  agent.py / cli.py  오케스트레이션
.github/workflows/   weekly.yml(매주 예측·배포), train.yml(분기 재학습)
```

## 중부권/남부권으로 확장

`config.yaml` 에서 `regions_active: [korea, central, south]` 로 바꾸고 `kwagent train` 을 다시 실행하세요.
권역은 행정구역 기준입니다(경북 안동은 남부). 지점은 `regions.py` 에서 추가할 수 있습니다.

## 정확도 개선 루프

1. 매주 `run` 이 4주 전 예측을 ERA5 로 채점해 `verification` 테이블에 기록합니다.
2. 검증 4건 이상: 역학모델 편향(기온·운량은 차이, 강수는 비율)을 계절별로 보정합니다.
3. 검증 8건 이상: 예측원 가중치를 사전값에서 최근 52주 RPSS 기반으로 바꿉니다.
4. 검증 20건 이상: 기후값으로 당기는 비율(α)을 RPS 최소화로 재추정합니다.
5. 분기마다 `train` 으로 통계모델을 다시 학습합니다.

## 한계

- 공개 API 는 '현재' 앙상블만 제공합니다. 과거 역학모델 예측으로 백테스트할 수 없어, 역학모델 보정은 운영하면서 쌓입니다(처음 2~3개월은 가중치를 낮게 시작).
- 정답이 ERA5(약 25 km 격자, 5일 지연)라서 지점 관측과 차이가 있습니다. 기상청 API허브 키를 받으면 ASOS 관측으로 바꾸는 것을 권장합니다.
- 운량은 ERA5 모델 운량입니다. 관측 운량(할)과 단위·정의가 다릅니다.
