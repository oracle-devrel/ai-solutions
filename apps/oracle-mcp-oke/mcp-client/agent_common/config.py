import os
import re
import urllib.parse
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
ORACLE_LOGO_PRIMARY_PATH = BASE_DIR / "assets" / "oracle-svg.svg"
ORACLE_LOGO_REMOTE_FALLBACK = "https://www.oracle.com/a/ocom/img/oracle-logo.svg"
DOWNLOADS_DIR = BASE_DIR / "downloads"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
OCID_RE = re.compile(r"ocid1\.(?:ai)?speechtranscriptionjob\.[A-Za-z0-9._-]+", re.IGNORECASE)
VALID_JOB_OCID_RE = re.compile(
    r"^ocid1\.(?:ai)?speechtranscriptionjob\.oc1\.[a-z0-9-]+\.[a-z0-9]+$",
    re.IGNORECASE,
)


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def env_bool(name: str, default: bool = False) -> bool:
    value = get_env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y"}


def resolve_public_mcp_url(default_url: str | None = None) -> str:
    for key in ("MCP_PUBLIC_URL", "MCP_EXTERNAL_URL", "PUBLIC_MCP_URL"):
        value = str(os.getenv(key) or "").strip()
        if value:
            return value
    return str(default_url or "").strip()


def resolve_public_inspector_ui_url(client_port: int) -> str:
    explicit = str(os.getenv("INSPECTOR_PUBLIC_URL") or "").strip()
    if explicit:
        return explicit
    base = str(os.getenv("INSPECTOR_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return f"{base}:{client_port}"
    return f"http://localhost:{client_port}"


def mask_ocid(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "<unset>"
    if len(raw) <= 28:
        return raw
    return f"{raw[:22]}...{raw[-6:]}"


def normalize_payload_keys(payload: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "compartmentId": "compartment_id",
        "namespaceName": "namespace",
        "bucketName": "bucket_name",
        "fileNames": "file_names",
        "fileName": "file_name",
        "filenameQuery": "filename_query",
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


def build_speech_config(
    *,
    model_type_default: str = "whisper-v3t",
    output_prefix_default: str | None = "output/",
    language_code_default: str | None = None,
    whisper_prompt_default: str | None = None,
    diarization_enabled_default: Any = None,
) -> dict[str, Any]:
    return {
        "compartment_id": get_env("SPEECH_COMPARTMENT_OCID") or get_env("COMPARTMENT_ID"),
        "namespace": get_env("OCI_NAMESPACE"),
        "bucket_name": get_env("SPEECH_BUCKET"),
        "job_name": get_env("SPEECH_JOB_NAME"),
        "output_prefix": get_env("SPEECH_OUTPUT_PREFIX", output_prefix_default),
        "model_type": get_env("SPEECH_MODEL_TYPE", model_type_default),
        "language_code": get_env("SPEECH_LANGUAGE_CODE", language_code_default),
        "whisper_prompt": get_env("SPEECH_WHISPER_PROMPT", whisper_prompt_default),
        "diarization_enabled": env_bool("SPEECH_DIARIZATION_ENABLED", diarization_enabled_default)
        if diarization_enabled_default is not None
        else None,
    }


def safe_object_basename(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "audio.bin"
    base = Path(raw).name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe or "audio.bin"


def logo_src_for_html() -> str:
    if ORACLE_LOGO_PRIMARY_PATH.exists():
        return f"/gradio_api/file={urllib.parse.quote(str(ORACLE_LOGO_PRIMARY_PATH))}"
    return ORACLE_LOGO_REMOTE_FALLBACK


def logo_src_for_avatar() -> str:
    if ORACLE_LOGO_PRIMARY_PATH.exists():
        return str(ORACLE_LOGO_PRIMARY_PATH)
    return ORACLE_LOGO_REMOTE_FALLBACK