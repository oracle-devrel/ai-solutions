import json
from typing import Any, Callable

from .config import build_speech_config, normalize_payload_keys
from .logging_utils import json_preview, parse_json, redact_for_logging
from .trace_store import pop_pending_uploaded_objects, shift_pending_uploaded_object


JOB_ID_TOOLS: set[str] = {
    "get_speech_transcription_job",
    "cancel_speech_transcription_job",
    "get_speech_transcription_text",
    "read_transcription_result",
}

TOOL_EXACT_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "process_audio": ("object_name",),
    "create_speech_transcription_job": ("file_names", "job_name"),
    "list_speech_transcription_jobs": ("compartment_id",),
    "list_bucket_audio_files": ("namespace", "bucket_name", "prefix"),
    "find_transcription_job_by_object": ("object_name",),
    "find_transcription_job_by_filename": ("filename",),
}

TOOL_ALLOWED_ARGS: dict[str, set[str]] = {
    "sentiment_analysis": {"text"},
    "upload_audio_to_bucket": {"file_path"},
    "process_audio": {"object_name", "payload"},
    "create_speech_transcription_job": {"file_names", "job_name", "payload"},
    "get_speech_transcription_job": {"job_id"},
    "list_speech_transcription_jobs": {"compartment_id", "payload"},
    "cancel_speech_transcription_job": {"job_id"},
    "get_speech_transcription_text": {"job_id"},
    "read_transcription_result": {"job_id"},
    "list_bucket_audio_files": {"namespace", "bucket_name", "prefix", "payload"},
    "find_transcription_job_by_object": {"object_name", "payload"},
    "find_transcription_job_by_filename": {"filename", "payload"},
}

_SPEECH_DEFAULT_KEYS: tuple[str, ...] = (
    "compartment_id",
    "namespace",
    "bucket_name",
    "job_name",
    "output_prefix",
    "model_type",
    "language_code",
    "whisper_prompt",
    "diarization_enabled",
)


def _apply_defaults(payload: dict[str, Any], cfg: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        if payload.get(key) in (None, "", []):
            default = cfg.get(key)
            if default not in (None, "", []):
                payload[key] = default
    return payload


def _extract_io_locations(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    input_location = payload.get("inputLocation") if isinstance(payload.get("inputLocation"), dict) else {}
    output_location = payload.get("outputLocation") if isinstance(payload.get("outputLocation"), dict) else {}
    return input_location, output_location


def _apply_speech_common_fields(payload: dict[str, Any], input_location: dict[str, Any], output_location: dict[str, Any]) -> None:
    if not payload.get("namespace"):
        payload["namespace"] = input_location.get("namespaceName") or output_location.get("namespaceName")
    if not payload.get("bucket_name"):
        payload["bucket_name"] = input_location.get("bucketName") or output_location.get("bucketName")
    if not payload.get("output_prefix"):
        payload["output_prefix"] = output_location.get("prefix")
    if not payload.get("model_type"):
        payload["model_type"] = payload.get("modelId")
    if not payload.get("language_code"):
        payload["language_code"] = payload.get("languageCode")
    if not payload.get("whisper_prompt"):
        payload["whisper_prompt"] = payload.get("whisperPrompt")
    if payload.get("diarization_enabled") is None and payload.get("diarizationEnabled") is not None:
        payload["diarization_enabled"] = payload.get("diarizationEnabled")


def _enrich_create_payload(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    input_location, output_location = _extract_io_locations(payload)
    if not payload.get("file_names"):
        object_name = str(input_location.get("objectName") or "").strip()
        if object_name:
            payload["file_names"] = [object_name]
    _apply_speech_common_fields(payload, input_location, output_location)
    payload = _apply_defaults(payload, cfg, _SPEECH_DEFAULT_KEYS)
    if not payload.get("file_names"):
        pending = pop_pending_uploaded_objects()
        if pending:
            payload["file_names"] = pending
    return payload


def _enrich_process_audio_payload(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    input_location, output_location = _extract_io_locations(payload)
    _apply_speech_common_fields(payload, input_location, output_location)
    payload = _apply_defaults(payload, cfg, _SPEECH_DEFAULT_KEYS)
    if not payload.get("object_name"):
        file_names = payload.get("file_names")
        if isinstance(file_names, list):
            payload["object_name"] = next((str(item).strip() for item in file_names if str(item).strip()), "")
        elif isinstance(file_names, str):
            payload["object_name"] = file_names.strip()
    if not payload.get("object_name"):
        next_uploaded = shift_pending_uploaded_object()
        if next_uploaded:
            payload["object_name"] = next_uploaded
    payload.pop("file_names", None)
    return payload


def _enrich_find_payload(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    filename = str(payload.get("filename") or "").strip()
    if not payload.get("object_name") and filename:
        payload["object_name"] = filename
    return _apply_defaults(payload, cfg, ("compartment_id", "namespace", "bucket_name", "output_prefix"))


def _enrich_list_payload(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    return _apply_defaults(payload, cfg, ("compartment_id", "namespace", "bucket_name", "output_prefix"))


PAYLOAD_TOOL_ENRICHERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "process_audio": _enrich_process_audio_payload,
    "create_speech_transcription_job": _enrich_create_payload,
    "find_transcription_job_by_filename": _enrich_find_payload,
    "find_transcription_job_by_object": _enrich_find_payload,
    "list_speech_transcription_jobs": _enrich_list_payload,
    "list_bucket_audio_files": _enrich_list_payload,
}


def is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def normalize_tool_payload(tool_name: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    cfg = build_speech_config()
    obj = normalize_payload_keys(dict(payload))
    enricher = PAYLOAD_TOOL_ENRICHERS.get(tool_name)
    if enricher:
        return enricher(obj, cfg)
    return obj


def normalize_payload_args(tool_name: str, args: dict[str, Any], logger: Any | None = None) -> dict[str, Any]:
    raw_args = dict(args or {})
    payload_value = args.get("payload")
    payload_obj: Any
    top_level_obj = normalize_payload_keys({k: v for k, v in raw_args.items() if k != "payload"})
    if payload_value is None:
        payload_obj = dict(top_level_obj)
    elif isinstance(payload_value, str):
        loaded = parse_json(payload_value)
        if isinstance(loaded, dict):
            payload_obj = loaded
        elif tool_name == "process_audio":
            payload_obj = dict(top_level_obj)
        elif tool_name in {"find_transcription_job_by_filename", "find_transcription_job_by_object"}:
            payload_obj = {"object_name": payload_value, "filename": payload_value}
        else:
            payload_obj = payload_value
    else:
        payload_obj = payload_value

    if isinstance(payload_obj, dict):
        nested_payload = payload_obj.get("payload")
        if isinstance(nested_payload, dict):
            payload_obj = nested_payload
        elif isinstance(nested_payload, str):
            loaded_nested = parse_json(nested_payload)
            if isinstance(loaded_nested, dict):
                payload_obj = loaded_nested

    normalized = normalize_tool_payload(tool_name, payload_obj)
    if isinstance(normalized, dict):
        for key, value in top_level_obj.items():
            if is_non_empty(value):
                normalized[key] = value

        exact_keys = TOOL_EXACT_ARG_KEYS.get(tool_name, ())
        normalized_args: dict[str, Any] = {}
        payload_rest = dict(normalized)

        if tool_name == "find_transcription_job_by_filename" and not is_non_empty(payload_rest.get("filename")):
            filename_fallback = str(
                payload_rest.get("filename")
                or payload_rest.get("file_name")
                or payload_rest.get("filename_query")
                or payload_rest.get("query")
                or payload_rest.get("object_name")
                or ""
            ).strip()
            if filename_fallback:
                payload_rest["filename"] = filename_fallback

        for key in exact_keys:
            value = payload_rest.pop(key, None)
            if is_non_empty(value):
                normalized_args[key] = value

        if tool_name == "find_transcription_job_by_filename":
            payload_rest.pop("object_name", None)
            payload_rest.pop("filename_query", None)
            payload_rest.pop("query", None)

        if payload_rest:
            normalized_args["payload"] = json.dumps(payload_rest)

        if logger is not None:
            logger.info(
                "[MCP][PAYLOAD_NORMALIZED] tool=%s before=%s after=%s",
                tool_name,
                json_preview(redact_for_logging(raw_args)),
                json_preview(redact_for_logging(normalized_args)),
            )
        return normalized_args

    if isinstance(payload_value, str):
        if tool_name == "process_audio":
            fallback = normalize_tool_payload(tool_name, dict(top_level_obj))
            if isinstance(fallback, dict):
                return {"payload": json.dumps(fallback)}
            return dict(top_level_obj)
        return {"payload": payload_value}
    return args


def validate_tool_args(tool_name: str, args: dict[str, Any], logger: Any | None = None) -> dict[str, Any]:
    allowed = TOOL_ALLOWED_ARGS.get(tool_name)
    if not allowed or not isinstance(args, dict):
        return args

    fixed = dict(args)
    unknown = [k for k in list(fixed.keys()) if k not in allowed]
    if not unknown:
        return fixed

    payload_obj: dict[str, Any] = {}
    payload_value = fixed.get("payload")
    if isinstance(payload_value, str):
        parsed = parse_json(payload_value)
        if isinstance(parsed, dict):
            payload_obj = dict(parsed)
    elif isinstance(payload_value, dict):
        payload_obj = dict(payload_value)

    for key in unknown:
        payload_obj[key] = fixed.pop(key)

    fixed["payload"] = json.dumps(payload_obj)
    if logger is not None:
        logger.info(
            "[MCP][ARG_VALIDATION] tool=%s unknown_top_level=%s repaired_args=%s",
            tool_name,
            unknown,
            json_preview(redact_for_logging(fixed)),
        )
    return fixed


def normalize_job_id_args(args: dict[str, Any]) -> dict[str, Any]:
    payload_dict = args.get("payload", {}) if isinstance(args.get("payload"), dict) else {}
    candidate = (
        args.get("job_id")
        or args.get("resolved_job_id")
        or args.get("jobId")
        or args.get("id")
        or payload_dict.get("job_id")
        or payload_dict.get("resolved_job_id")
    )
    job_id = str(candidate or "").strip().rstrip(".,;:)]}")
    if job_id:
        return {"job_id": job_id}
    return args
