"""저작권 표시와 AI·자동 수집 거부 (2026-11-24 사용자 요청).

공개 웹사이트는 기술적으로 복사를 완전히 막을 수 없다. 여기서는
  (1) 권리를 분명히 밝혀 법적 근거를 만들고(화면 꼬리말·이용약관·엑셀 '저작권' 시트·그래프 워터마크),
  (2) 규칙을 지키는 AI 수집 로봇이 가져가지 않게 신호를 준다(robots.txt·noai 메타·TDMRep).
원자료(ERA5, Open-Meteo 등)의 권리는 각 기관에 있으므로 출처 표시는 그대로 두고,
권리 주장은 이 사이트가 만든 결과물(예측 확률·해설·화면 디자인·코드)에만 한다.
"""
from __future__ import annotations

from pathlib import Path

OWNER = "dhpaeng81-crypto"
YEAR = 2026
SITE_URL = "https://dhpaeng81-crypto.github.io/kwagent/"
COPYRIGHT = f"© {YEAR} {OWNER}"
NOTICE = (f"{COPYRIGHT}. All rights reserved. 이 사이트의 예측 결과·해설·화면·엑셀 자료의 무단 전재·재배포·"
          "상업적 이용과 AI 학습·자동 수집(크롤링·스크래핑)을 금지합니다.")
SOURCES = ("원자료: ERA5(Copernicus 기후변화서비스), ECMWF·NOAA·DWD 예측(Open-Meteo 경유, CC BY 4.0), "
           "NOAA CPC 기후지수 — 원자료의 권리는 각 기관에 있습니다.")

# 머리(head)에 넣는 표시: 일반 검색은 허용, AI 학습·데이터마이닝은 거부
HEAD_META = (f'<meta name="copyright" content="{COPYRIGHT}">'
             f'<meta name="author" content="{OWNER}">'
             '<meta name="robots" content="index, follow, noai, noimageai">'
             '<meta name="tdm-reservation" content="1">'
             f'<meta name="tdm-policy" content="{SITE_URL}terms.html">')

# AI 학습·수집 로봇 (2026년 기준 알려진 이름). 일반 검색 로봇(Googlebot, Yeti(네이버), Bingbot 등)은 허용.
AI_BOTS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-Web", "Claude-User", "Claude-SearchBot",
    "anthropic-ai", "Google-Extended", "GoogleOther", "GoogleOther-Image", "GoogleOther-Video", "Google-CloudVertexBot",
    "CCBot", "PerplexityBot", "Perplexity-User", "Bytespider", "TikTokSpider", "Amazonbot", "Applebot-Extended",
    "meta-externalagent", "meta-externalfetcher", "FacebookBot", "cohere-ai", "cohere-training-data-crawler",
    "Diffbot", "ImagesiftBot", "Omgilibot", "omgili", "YouBot", "AI2Bot", "Ai2Bot-Dolma", "Timpibot",
    "MistralAI-User", "DuckAssistBot", "PanguBot", "Kangaroo Bot", "img2dataset", "Scrapy", "Webzio-Extended",
    "iaskspider", "ICC-Crawler", "VelenPublicWebCrawler", "Sidetrade indexer bot", "QualifiedBot", "Brightbot",
    "FriendlyCrawler", "Crawlspace", "SemrushBot-OCOB", "Factset_spyderbot", "AwarioBot", "Novellum",
]


def robots_txt() -> str:
    lines = ["# AI 학습·데이터 수집 로봇은 이 사이트 전체를 가져갈 수 없습니다. (" + COPYRIGHT + ")", ""]
    for b in AI_BOTS:
        lines.append(f"User-agent: {b}")
    lines += ["Disallow: /", "", "# 일반 검색은 허용, 엑셀 원자료는 수집 제외", "User-agent: *",
              "Disallow: /kwagent/*.xlsx$", "Allow: /", ""]
    return "\n".join(lines)


def ai_txt() -> str:
    return (f"# ai.txt — {COPYRIGHT}\n# AI 학습·데이터마이닝 사용을 허락하지 않습니다.\n"
            "User-Agent: *\nDisallow: /\nDisallow: *\n")


def tdmrep_json() -> str:
    # W3C TDMRep: 경로별 텍스트·데이터마이닝 권리 유보(EU 저작권 지침 4조 opt-out)
    return ('[{"location": "/*", "tdm-reservation": 1, "tdm-policy": "' + SITE_URL + 'terms.html"}]\n')


def root_files(out: Path) -> list[Path]:
    """도메인 맨 앞(dhpaeng81-crypto.github.io)에 둘 파일들. 하위 폴더의 robots.txt 는 로봇이 읽지 않는다."""
    out.mkdir(parents=True, exist_ok=True)
    (out / ".well-known").mkdir(exist_ok=True)
    files = {
        "robots.txt": robots_txt(),
        "ai.txt": ai_txt(),
        ".well-known/tdmrep.json": tdmrep_json(),
        ".nojekyll": "",                       # 점으로 시작하는 폴더(.well-known)도 게시되게
        "index.html": ('<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/kwagent/">'
                       f'<meta name="robots" content="noai, noimageai"><title>한국 기상전망</title>'
                       '<a href="/kwagent/">한국 기상전망으로 이동</a>'),
    }
    paths = []
    for name, text in files.items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return paths


def stamp_xlsx(path) -> None:
    """엑셀에 '저작권' 시트와 문서 정보를 넣는다."""
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font
    wb = load_workbook(path)
    ws = wb.create_sheet("저작권")
    rows = [("저작권", NOTICE), ("이용 조건", "개인적인 열람·참고만 허용합니다. 인용할 때는 출처(" + SITE_URL + ")를 밝혀 주세요. "
                                          "재배포·판매·서비스 제공·AI 학습 데이터로 사용하려면 사전 서면 허락이 필요합니다."),
            ("원자료", SOURCES), ("면책", "공식 기상예보가 아닌 참고용입니다. 이 자료로 생긴 손해에 책임지지 않습니다.")]
    for i, (k, v) in enumerate(rows, start=1):
        ws.cell(i, 1, k).font = Font(bold=True)
        c = ws.cell(i, 2, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 48
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 100
    p = wb.properties
    p.creator = OWNER
    p.lastModifiedBy = OWNER
    p.description = NOTICE
    p.keywords = "copyright reserved; noai; no-tdm"
    wb.save(path)


TERMS_HTML = f"""
<h1>이용약관과 저작권</h1>
<div class='card terms'>
<h3>1. 저작권</h3>
<p>{NOTICE}</p>
<p>이 사이트의 예측 확률, 경향, 자동 해설, 화면 구성·디자인, 아이콘, 엑셀 자료, 그리고 이를 만드는 프로그램은
{OWNER}의 저작물입니다.</p>
<h3>2. 허용하는 이용</h3>
<ul><li>개인이 날씨를 참고하려고 보는 것</li>
<li>출처(<a href="{SITE_URL}">{SITE_URL}</a>)를 밝히고 일부를 인용하는 것(보도·연구·교육 목적의 짧은 인용)</li></ul>
<h3>3. 금지하는 이용</h3>
<ul><li>내용·자료의 전부 또는 상당 부분을 복제·재배포·판매하거나, 다른 서비스·앱·웹사이트에 싣는 것</li>
<li>로봇·프로그램으로 자동 수집(크롤링·스크래핑)하는 것</li>
<li><b>인공지능(AI)·기계학습 모델의 학습, 미세조정, 검색 증강(RAG), 평가 데이터로 쓰는 것</b>,
그리고 텍스트·데이터 마이닝(TDM). 저작권자는 대한민국 저작권법과 EU 디지털 단일시장 저작권 지침 제4조에 따라
텍스트·데이터 마이닝 권리를 명시적으로 유보합니다(TDM Reservation).</li>
<li>사전 서면 허락 없는 상업적 이용</li></ul>
<h3>4. 원자료와 출처</h3>
<p>{SOURCES} 원자료는 각 기관의 이용 조건을 따릅니다. 이 사이트는 이를 가공해 새로운 예측 결과를 만듭니다.</p>
<h3>5. 면책</h3>
<p>이 사이트는 공식 기상예보가 아닌 참고용 정보입니다. 특보·위험 기상은 기상청 발표를 따르세요.
이 정보의 이용으로 생긴 손해에 대해 책임지지 않습니다.</p>
<h3>6. 문의</h3>
<p>허락이 필요한 이용은 GitHub(<a href="https://github.com/{OWNER}">github.com/{OWNER}</a>)로 문의해 주세요.</p>
</div>
"""
