"""LLM 해설: 확률표·기후지수·검증 성적을 읽고 기상청 전망문 형식의 한국어 해설을 쓴다.

숫자는 바꾸지 않고 해석만 하도록 제한한다. ANTHROPIC_API_KEY 가 없으면 규칙 기반 요약으로 대체.
"""
from __future__ import annotations

import json
import logging
import os

from .report import VAR_LABEL, _verdict, result_vars
from .regions import REGION_LABELS

log = logging.getLogger(__name__)

SYSTEM = """당신은 기상청 기후예측과 예보관입니다. 주어진 JSON 의 확률 수치만 근거로
1개월(주별 4주) 전망 해설을 한국어로 씁니다.
규칙:
- 확률·평년범위 숫자를 바꾸거나 새로 만들지 마세요.
- 주별로 기온·운량·일사량·강수량·강수형태(비/눈)를 각 1~2문장으로 쓰고, 근거가 되는 기후지수
  (Niño3.4, AO, MJO)를 일반적인 기후학 지식 수준에서만 설명하세요. 확실하지 않은 인과는 '가능성'으로 표현하세요.
- 3~4주차는 예측성이 낮다는 점을 밝히고, 확률이 40% 이하로 고르면 '불확실성이 크다'고 쓰세요.
- 마지막에 '검증 현황' 한 문단: verification 의 RPSS(0보다 크면 평년 예보보다 나음)를 그대로 인용.
- 형식: 마크다운, 제목 '## 해설', 600~900자."""


def rule_based(result: dict) -> str:
    lines = ["## 해설 (자동 요약)"]
    for region, rd in result["regions"].items():
        lines.append(f"**{REGION_LABELS.get(region, region)}**")
        for wk in rd["weeks"]:
            parts = [f"{VAR_LABEL[v][0]} {_verdict(wk['vars'][v]['display'], v)}"
                     for v in result_vars(rd)]
            p = wk["ptype"]
            if p["p_snow"] >= 0.3:
                parts.append(f"눈 올 확률 {p['p_snow']*100:.0f}%")
            lines.append(f"- {wk['label']}: " + ", ".join(parts))
    return "\n".join(lines)


def write(result: dict, cfg, verification: list[dict] | None = None) -> str:
    nc = cfg.get("narrative", {})
    if not nc.get("enabled", True) or not os.environ.get("ANTHROPIC_API_KEY"):
        return rule_based(result)
    try:
        import anthropic
        client = anthropic.Anthropic()
        payload = {"forecast": result, "verification": verification or []}
        msg = client.messages.create(
            model=nc.get("model", "claude-sonnet-5-5"), max_tokens=int(nc.get("max_tokens", 1500)),
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # pragma: no cover - network
        log.warning("LLM 해설 실패, 규칙 기반으로 대체: %s", e)
        return rule_based(result)
