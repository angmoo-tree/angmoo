from __future__ import annotations




def _feed_history_sanitize_stream_params() -> dict[str, str]:
    return {"googleResponseMode": "non_streaming"}


def _feed_scan_stream_params() -> dict[str, str]:
    return {"googleResponseMode": "non_streaming"}


def _tool_choice_any(tools_allow: list[str]) -> dict[str, object]:
    return {"mode": "ANY", "allowedFunctionNames": tools_allow}
