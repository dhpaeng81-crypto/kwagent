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
    for name, sel in (("이번 주", [d for d in days if d["lead"] <= 7]), ("다음 주", [d for d in days if d["lead"] > 7])):
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
    rain = [d for d in days if (d["vars"].get("precip") or {}).get("pop", 0) >= 0.4]
    snow = [d for d in days if (d["vars"].get("precip") or {}).get("p_snow", 0) >= 0.2]
    if snow:
        out.append(("snow", f"눈 가능성: {_dates(snow)}"))
    if rain:
        out.append(("rain", f"비 소식: {_dates(rain)}"))
    elif not snow:
        out.append(("calm", "2주 동안 큰 비 소식 없음"))
    return out
