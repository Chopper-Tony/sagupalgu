"""툴 공통 헬퍼 — _make_tool_call, _extract_json"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _make_tool_call(
    tool_name: str,
    input_data: Dict[str, Any],
    output: Any,
    success: bool,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_name,
        "input": input_data,
        "output": output,
        "success": success,
        "error": error,
    }


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}
