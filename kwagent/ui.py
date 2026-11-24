"""웹사이트용 작은 부품: 날씨 그림(SVG), 2주 일별 '한눈에' 요약 문장."""
from __future__ import annotations

_SUN = ('<circle cx="{x}" cy="{y}" r="{r}" fill="#f6b51e"/>'
        '<g stroke="#f6b51e" stroke-width="2.4" stroke-linecap="round">{rays}</g>')
_CLOUD = ('<g fill="{c}"><circle cx="15" cy="25" r="7"/><circle cx="23" cy="20" r="9"/>'
          '<circle cx="31" cy="25.5" r="6.5"/><rect x="8" y="24" width="30" height="9" rx="4.5"/></g>')


def _rays(cx, cy, r0, r1):
    import math
    out = []
    for k in range(8):
        a = k * math.pi / 4
        out.append(f'<line x1="{cx + r0 * math.cos(a):.1f}" y1="{cy + r0 * math.sin(a):.1f}" '
                   f'x2="{cx + r1 * math.cos(a):.1f}" y2="{cy + r1 * math.sin(a):.1f}"/>')
    return "".join(out)


def wx_kind(day: dict) -> str:
    """하루 예측 → 날씨 그림 종류: sun | partly | cloud | rain | snow | shower."""
    v = day["vars"]
    p = v.get("precip") or {}
    pop, snow = p.get("pop") or 0, p.get("p_snow") or 0
    sky = (v.get("cloud") or {}).get("sky") or {}
    if pop >= 0.4:
        return "snow" if snow >= 0.5 * pop else "rain"
    if pop >= 0.25:
        return "shower"
    top = max(sky, key=sky.get) if sky else "맑음"
    return {"맑음": "sun", "구름많음": "partly", "흐림": "cloud"}.get(top, "partly")


WX_LABEL = {"sun": "맑음", "partly": "구름많음", "cloud": "흐림", "rain": "비", "snow": "눈", "shower": "비 조금"}


def wx_icon(kind: str, size: int = 34) -> str:
    sun = _SUN.format(x=17, y=15, r=6.5, rays=_rays(17, 15, 9.5, 12.5))
    body = {
        "sun": _SUN.format(x=22, y=22, r=8.5, rays=_rays(22, 22, 12, 16)),
        "partly": sun + _CLOUD.format(c="#c9d3de").replace('cx="15"', 'cx="17"'),
        "cloud": _CLOUD.format(c="#aab6c4"),
        "shower": sun + _CLOUD.format(c="#b9c4d0")
        + '<g stroke="#3a7bd5" stroke-width="2.4" stroke-linecap="round"><line x1="20" y1="36" x2="18" y2="40"/></g>',
        "rain": _CLOUD.format(c="#9aa7b6")
        + '<g stroke="#3a7bd5" stroke-width="2.4" stroke-linecap="round"><line x1="15" y1="36" x2="13" y2="41"/>'
          '<line x1="23" y1="36" x2="21" y2="41"/><line x1="31" y1="36" x2="29" y2="41"/></g>',
        "snow": _CLOUD.format(c="#9aa7b6")
        + '<g fill="#6aa0e8"><circle cx="15" cy="38" r="2"/><circle cx="23" cy="40" r="2"/><circle cx="31" cy="38" r="2"/></g>',
    }[kind]
    return (f'<svg class="wx" viewBox="0 0 44 44" width="{size}" height="{size}" role="img" '
            f'aria-label="{WX_LABEL[kind]}">{body}</svg>')


def _dates(days) -> str:
    names = [d["label"].split("(")[0] + f"({d['label'][-2]})" for d in days]
    return ", ".join(names[:3]) + (f" 외 {len(names) - 3}일" if len(names) > 3 else "")


def daily_headlines(days: list[dict]) -> list[tuple[str, str]]:
    """2주 일별 예측의 핵심을 2~4줄로: [(종류, 문장)]. 종류는 warm|cool|rain|snow|calm."""
    out = []
    near = [d for d in days if "trend" not in d]
    for name, sel in (("이번 주", [d for d in near if d["lead"] <= 7]), ("다음 주", [d for d in near if d["lead"] > 7])):
        an = [d["vars"]["tmax"]["q50"] - d["vars"]["tmax"]["normal"] for d in sel
              if d["vars"].get("tmax") and d["vars"]["tmax"].get("normal") is not None]
        if not an:
            continue
        m = sum(an) / len(an)
        if m >= 1.5:
            out.append(("warm", f"{name}는 평년보다 따뜻 (낮 최고 평균 +{m:.0f}°C)"))
        elif m <= -1.5:
            out.append(("cool", f"{name}는 평년보다 쌀쌀 (낮 최고 평균 {m:.0f}°C)"))
        else:
            out.append(("calm", f"{name} 기온은 평년과 비슷"))
    rain = [d for d in near if (d["vars"].get("precip") or {}).get("pop", 0) >= 0.4]
    snow = [d for d in near if (d["vars"].get("precip") or {}).get("p_snow", 0) >= 0.2]
    if snow:
        out.append(("snow", f"눈 가능성: {_dates(snow)}"))
    if rain:
        out.append(("rain", f"비 소식: {_dates(rain)}"))
    elif not snow:
        out.append(("calm", "2주 동안 큰 비 소식 없음"))
    far = [d for d in days if "trend" in d and "temp" in d["trend"]]
    if far:
        hi = sum(d["trend"]["temp"]["p"][2] for d in far) / len(far)
        lo = sum(d["trend"]["temp"]["p"][0] for d in far) / len(far)
        span = f"{far[0]['label'].split('(')[0]}~{far[-1]['label'].split('(')[0]}"
        if hi - lo >= 0.15:
            out.append(("warm", f"3~4주 뒤({span})도 평년보다 따뜻할 가능성 ({hi*100:.0f}%)"))
        elif lo - hi >= 0.15:
            out.append(("cool", f"3~4주 뒤({span})는 평년보다 쌀쌀할 가능성 ({lo*100:.0f}%)"))
        else:
            out.append(("calm", f"3~4주 뒤({span}) 기온은 뚜렷한 경향 없음"))
    return out


TREND_WORDS = {"temp": ("쌀쌀", "비슷", "따뜻"), "precip": ("건조", "비슷", "비 많음"),
               "cloud": ("구름 적음", "비슷", "구름 많음"), "srad": ("햇빛 적음", "비슷", "햇빛 많음")}


def trend_cell(tr: dict | None, var: str) -> tuple[str, str, float, str]:
    """경향 달력 한 칸: (말, 색, 진하기, 확률 글자). 가장 큰 쪽 확률이 45% 미만이면 '불확실'."""
    if not tr:
        return "-", "#e5e8ec", 0.0, ""
    p = tr["p"]
    i = max(range(3), key=lambda k: p[k])
    col = CAT_COLORS.get(var, CAT_COLORS["temp"])
    if p[i] < 0.45:
        return "불확실", "#c7cdd4", 0.15, f"{p[i]*100:.0f}%"
    return TREND_WORDS[var][i], col[i], max(0.0, min(1.0, (p[i] - 0.4) / 0.35)), f"{p[i]*100:.0f}%"


# ---------------------------------------------------------------- 1개월 전망 '한눈에'
# 변수별 쉬운 말: (낮을 때, 높을 때)
MONTH_WORDS = {"temp": ("쌀쌀", "따뜻"), "cloud": ("구름 적음", "구름 많음"),
               "srad": ("햇빛 적음", "햇빛 많음"), "precip": ("건조", "비 많음")}
CAT_COLORS = {"temp": ("#3d6fc4", "#9aa3ac", "#c9473b"), "precip": ("#9c6b3c", "#9aa3ac", "#2e8a5a"),
              "cloud": ("#c99a2e", "#9aa3ac", "#56657a"), "srad": ("#6f7d96", "#9aa3ac", "#d9831a")}


def month_chips(rd: dict, vars_: list[str]) -> list[tuple[str, str, str]]:
    """4주 전체 경향을 짧은 말로: [(변수, 색, 말)]. 높음-낮음 확률 차이의 4주 평균으로 판단."""
    out = []
    for v in vars_:
        w = [wk["vars"][v]["prob"] for wk in rd["weeks"] if v in wk["vars"]]
        if not w:
            continue
        tend = sum(p[2] - p[0] for p in w) / len(w)
        early = sum(p[2] - p[0] for p in w[:2]) / max(1, len(w[:2]))
        late = sum(p[2] - p[0] for p in w[2:]) / max(1, len(w[2:]))
        lo, hi = MONTH_WORDS.get(v, ("낮음", "높음"))
        col = CAT_COLORS.get(v, CAT_COLORS["temp"])
        if early > 0.15 and late < -0.15 or early < -0.15 and late > 0.15:
            word = f"초반 {hi if early > 0 else lo} → 후반 {hi if late > 0 else lo}"
            c = col[1]
        elif abs(tend) <= 0.12:
            word = {"temp": "기온 평년 수준", "cloud": "구름 평년 수준", "srad": "햇빛 평년 수준",
                    "precip": "강수 평년 수준"}.get(v, "평년 수준")
            c = col[1]
        else:
            word = ("" if abs(tend) > 0.3 else "대체로 ") + (hi if tend > 0 else lo)
            c = col[2] if tend > 0 else col[0]
        out.append((v, c, word))
    return out


def month_cell(display: list[int], var: str, cats: tuple[str, str, str]) -> tuple[str, str, float]:
    """색깔표 한 칸: (말, 배경색, 진하기 0~1). 같은 확률이 겹치면 '비슷~높음'처럼."""
    order = sorted(range(3), key=lambda k: -display[k])
    i = order[0]
    col = CAT_COLORS.get(var, CAT_COLORS["temp"])
    if display[order[0]] == display[order[1]]:
        a, b = sorted(order[:2])
        return f"{cats[a]}~{cats[b]}", "#9aa3ac", 0.25
    strength = max(0.0, min(1.0, (display[i] - 33) / 40))   # 40%면 옅게, 70% 이상이면 진하게
    return cats[i], col[i], strength
