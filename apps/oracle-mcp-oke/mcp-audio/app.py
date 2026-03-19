import json
import os
from typing import Any

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from tools.logger_util import get_logger
from tools.speech_transcription import handle_process_audio
from tools.text_analysis import analyze_text

logger = get_logger(__name__)

APP_NAME = os.getenv("FASTMCP_APP_NAME", "mcp-audio")
PORT = int(os.getenv("FASTMCP_PORT", "8080"))
HOST = os.getenv("FASTMCP_HOST", "0.0.0.0")
TRANSPORT = os.getenv("FASTMCP_TRANSPORT", "http").strip().lower().replace("_", "-")

mcp = FastMCP(APP_NAME)


def _compartment_id() -> str | None:
    return os.getenv("COMPARTMENT_ID")


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _normalize_payload_keys(payload: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "compartmentId": "compartment_id",
        "namespaceName": "namespace",
        "bucketName": "bucket_name",
        "fileName": "file_name",
        "objectName": "object_name",
        "jobName": "job_name",
        "modelType": "model_type",
        "modelId": "model_type",
        "languageCode": "language_code",
        "whisperPrompt": "whisper_prompt",
        "diarizationEnabled": "diarization_enabled",
        "outputPrefix": "output_prefix",
    }
    normalized: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        normalized[key_map.get(str(key), str(key))] = value
    return normalized


def _parse_payload_json(payload: str | None) -> dict[str, Any]:
    if payload is None:
        return {}
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        return {}

    nested = parsed.get("payload")
    if isinstance(nested, dict):
        return _normalize_payload_keys(dict(nested))
    if isinstance(nested, str):
        try:
            nested_parsed = json.loads(nested)
            if isinstance(nested_parsed, dict):
                return _normalize_payload_keys(dict(nested_parsed))
        except json.JSONDecodeError:
            pass
    return _normalize_payload_keys(dict(parsed))


def _merge_payload_from_args(payload: str | None, exact_args: dict[str, Any]) -> str:
    merged = _parse_payload_json(payload)
    normalized_exact = _normalize_payload_keys(dict(exact_args))

    for key, value in normalized_exact.items():
        if _is_non_empty(value):
            merged[key] = value

    return json.dumps(merged)


@mcp.tool
def sentiment_analysis(text: str) -> str:
    """Analyze sentiment and key phrases for input text."""
    return json.dumps(analyze_text(text))


@mcp.tool
async def process_audio(
    object_name: str | None = None,
    file_name: str | None = None,
    audio_base64: str | None = None,
    payload: str | None = None,
    ctx: Context | None = None,
) -> str:
    """End-to-end audio processing: upload (optional), create job, poll, and fetch transcript."""
    try:
        merged_payload = _merge_payload_from_args(
            payload,
            {"object_name": object_name, "file_name": file_name, "audio_base64": audio_base64},
        )
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON payload", "hint": "Pass valid JSON string or omit payload."})

    merged_obj = _parse_payload_json(merged_payload)
    if _is_non_empty(merged_obj.get("file_name")) and _is_non_empty(merged_obj.get("audio_base64")):
        merged_obj.pop("object_name", None)
        merged_payload = json.dumps(merged_obj)

    return await handle_process_audio(merged_payload, ctx=ctx)


@mcp.resource("config://oci-defaults")
def oci_config_resource() -> str:
    """OCI default config exposed as MCP resource."""

    def _bool_env(name: str, default: bool) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "y"}

    return json.dumps(
        {
            "compartment_id": _compartment_id(),
            "namespace": os.getenv("OCI_NAMESPACE"),
            "bucket_name": os.getenv("SPEECH_BUCKET"),
            "available_models": ["ORACLE", "WHISPER_MEDIUM", "WHISPER_LARGE_V2", "WHISPER_LARGE_V3T"],
            "default_model": os.getenv("SPEECH_MODEL_TYPE", "WHISPER_LARGE_V3T"),
            "default_language": os.getenv("SPEECH_LANGUAGE_CODE", "auto"),
            "diarization_default": _bool_env("SPEECH_DIARIZATION_ENABLED", True),
        }
    )


@mcp.resource("docs://oracle-speech")
def oracle_docs_resource() -> str:
    """Oracle Speech and SDK references."""
    return json.dumps(
        {
            "speech_overview": "https://docs.oracle.com/en-us/iaas/Content/speech/using/using-jobs.htm",
            "create_jobs": "https://docs.oracle.com/en-us/iaas/Content/speech/using/create-trans-job.htm",
            "view_jobs": "https://docs.oracle.com/en-us/iaas/Content/speech/using/job-viewing.htm",
            "models_guide": "https://docs.oracle.com/en-us/iaas/Content/speech/using/speech.htm",
            "python_sdk": "https://docs.oracle.com/en-us/iaas/tools/python/latest/",
            "architecture": "https://docs.oracle.com/en/solutions/ai-speech/index.html",
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

async def main():
    if TRANSPORT not in {"http", "streamable-http"}:
        raise ValueError(
            f"Unsupported FASTMCP_TRANSPORT={TRANSPORT!r}. Use 'http' or 'streamable-http'."
        )
    await mcp.run_async(
        host=HOST,
        port=PORT,
        transport=TRANSPORT,
        stateless_http=True
    )


if __name__ == "__main__":
    import asyncio
    logger.info(
        "Starting MCP audio server | host=%s | port=%s | transport=%s",
        HOST,
        PORT,
        TRANSPORT,
    )
#app = mcp.http_app()

    #mcp.run(transport=TRANSPORT, host=HOST, port=PORT)
    asyncio.run(main())
    
