from __future__ import annotations

import inspect
from typing import Any


def prepare_agent_model(llm: Any, logger: Any) -> Any:
    bind_tools_fn = getattr(llm, "bind_tools", None)
    if not callable(bind_tools_fn):
        return llm

    bind_tools_cls_fn = getattr(llm.__class__, "bind_tools", None)
    if not callable(bind_tools_cls_fn):
        return llm

    try:
        signature = inspect.signature(bind_tools_cls_fn)
        supported_kwargs = set(signature.parameters.keys())
    except Exception:
        supported_kwargs = set()

    if "tool_choice" in supported_kwargs and "strict" in supported_kwargs:
        return llm

    if getattr(llm.__class__, "_oracle_bind_tools_compat_patched", False):
        return llm

    original_bind_tools = bind_tools_cls_fn

    def bind_tools_compat(self: Any, tools: Any, **kwargs: Any) -> Any:
        filtered_kwargs = dict(kwargs)
        dropped: list[str] = []
        for key in ("tool_choice", "strict"):
            if key in filtered_kwargs and key not in supported_kwargs:
                dropped.append(key)
                filtered_kwargs.pop(key, None)
        if dropped:
            logger.info("Agent model bind_tools compatibility: dropped unsupported kwargs=%s", ",".join(dropped))
        return original_bind_tools(self, tools, **filtered_kwargs)

    setattr(llm.__class__, "bind_tools", bind_tools_compat)
    setattr(llm.__class__, "_oracle_bind_tools_compat_patched", True)
    logger.info("Patched %s.bind_tools for create_agent compatibility", llm.__class__.__name__)
    return llm