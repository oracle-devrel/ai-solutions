import json
import logging
from pathlib import Path
from typing import Any


def configure_logging(log_file_name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file_name), logging.StreamHandler()],
    )
    return logging.getLogger(__name__)


def short_text(value: str, limit: int = 180) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def json_preview(value: Any, limit: int = 1200) -> str:
    try:
        raw = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        raw = str(value)
    return short_text(raw, limit)


def parse_json(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def redact_for_logging(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if key_s.lower() == "authorization" and isinstance(item, str):
                token = item.strip()
                if token.lower().startswith("bearer "):
                    bearer_value = token[7:].strip()
                    redacted[key_s] = f"Bearer {bearer_value[:12]}..." if bearer_value else "Bearer <empty>"
                else:
                    redacted[key_s] = "<redacted>"
                continue
            if key_s == "audio_base64":
                redacted[key_s] = "<redacted_base64>"
                continue
            if key_s == "payload" and isinstance(item, str):
                parsed = parse_json(item)
                if isinstance(parsed, dict):
                    redacted[key_s] = json.dumps(redact_for_logging(parsed), ensure_ascii=False)
                    continue
            redacted[key_s] = redact_for_logging(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_logging(item) for item in value]
    return value