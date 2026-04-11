from __future__ import annotations

import json
import re
from typing import Any

import structlog

from trove.ai import client as ai_client

log = structlog.get_logger()

SYSTEM = (
    "You are a media quality ranker. Given a list of release titles and a user query, "
    "score each release from 0 to 100 where higher is better. Consider resolution "
    "(2160p > 1080p > 720p), codec (x265/HEVC is efficient), remux > BluRay > WEB-DL > "
    "WEBRip > HDTV, and avoid CAM/TS/telesync. Respond with JSON only: a list of "
    "objects with keys 'index' and 'score'."
)


def _extract_json(text: str) -> list[dict[str, Any]] | None:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data
    return None


async def rerank(hits: list[Any], query: str) -> list[Any]:
    if not hits:
        return hits
    top = hits[:20]
    prompt_lines = [f"Query: {query}", "Releases:"]
    for i, h in enumerate(top):
        prompt_lines.append(f"[{i}] {getattr(h, 'title', '')} ({getattr(h, 'size', '?')}B)")
    prompt = "\n".join(prompt_lines)
    prompt += '\n\nRespond ONLY with JSON list: [{"index": 0, "score": 85}, ...]'

    try:
        response = await ai_client.complete(prompt, system=SYSTEM, temperature=0.1)
    except Exception as e:
        log.warning("ai.ranker.failed", error=str(e))
        return hits

    scores = _extract_json(response)
    if not scores:
        return hits

    adjustments: dict[int, float] = {}
    for item in scores:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = item.get("score")
        if isinstance(idx, int) and isinstance(score, (int, float)) and 0 <= idx < len(top):
            adjustments[idx] = float(score)

    for i, h in enumerate(top):
        if i in adjustments:
            # Blend AI score 50/50 with rule-based score.
            original = getattr(h, "score", 0.0) or 0.0
            if hasattr(h, "score"):
                h.score = (original + adjustments[i]) / 2

    reranked = sorted(top, key=lambda h: getattr(h, "score", 0.0), reverse=True)
    return reranked + hits[20:]
