import json
import os
import threading
import time
import inspect
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import oci

from tools.logger_util import get_logger
from tools.oci_auth import load_runtime_oci_config_and_signer

logger = get_logger(__name__)

MODEL_ALIAS_MAPPING: dict[str, dict[str, str]] = {
    "whisper-v3t": {
        "model_type": "WHISPER_LARGE_V3T",
        "domain": "GENERIC",
        "model_version": "1",
    },
    "whisper-v3t-medical": {
        "model_type": "WHISPER_LARGE_V3T",
        "domain": "GENERIC",
        "model_version": "MEDICAL__25071800",
    },
}

_CLIENT_LOCK = threading.Lock()
_SPEECH_CLIENT: oci.ai_speech.AIServiceSpeechClient | None = None
_SPEECH_CLIENT_CTX: tuple[str, str, str, str] | None = None
_OS_CLIENT: oci.object_storage.ObjectStorageClient | None = None
_OS_CLIENT_CTX: tuple[str, str, str, str] | None = None


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _bool_from_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _speech_defaults() -> dict[str, Any]:
    return {
        "compartment_id": _get_env("SPEECH_COMPARTMENT_OCID") or _get_env("COMPARTMENT_ID"),
        "namespace": _get_env("OCI_NAMESPACE"),
        "bucket_name": _get_env("SPEECH_BUCKET"),
        "job_name": _get_env("SPEECH_JOB_NAME"),
        "output_prefix": _get_env("SPEECH_OUTPUT_PREFIX", "output/"),
        "model_type": _get_env("SPEECH_MODEL_TYPE", "whisper-v3t"),
        "language_code": _get_env("SPEECH_LANGUAGE_CODE"),
        "whisper_prompt": None,
        "diarization_enabled": None,
        "input_prefix": _get_env("SPEECH_INPUT_PREFIX", "uploads"),
    }


def _resolve_compartment_id(overrides: dict[str, Any] | None = None) -> str | None:
    overrides = overrides or {}
    return (
        overrides.get("compartment_id")
        or _get_env("SPEECH_COMPARTMENT_OCID")
        or _get_env("COMPARTMENT_ID")
    )


def _client_context() -> tuple[str, str, str, str]:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    oci_config_file = os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
    region = os.environ.get("OCI_REGION", "")
    profile = os.environ.get("OCI_CONFIG_PROFILE", "").strip()
    return environment, oci_config_file, region, profile


def _build_speech_client() -> oci.ai_speech.AIServiceSpeechClient:
    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=240.0,
    )
    logger.info("Speech client auth mode=%s region=%s", auth_mode, config.get("region"))
    client_kwargs = {"config": config}
    if signer is not None:
        client_kwargs["signer"] = signer
    return oci.ai_speech.AIServiceSpeechClient(**client_kwargs)


def create_speech_client() -> oci.ai_speech.AIServiceSpeechClient:
    global _SPEECH_CLIENT, _SPEECH_CLIENT_CTX
    ctx = _client_context()
    with _CLIENT_LOCK:
        if _SPEECH_CLIENT is None or _SPEECH_CLIENT_CTX != ctx:
            _SPEECH_CLIENT = _build_speech_client()
            _SPEECH_CLIENT_CTX = ctx
    return _SPEECH_CLIENT


def _build_os_client() -> oci.object_storage.ObjectStorageClient:
    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=240.0,
    )
    logger.info("Object Storage client auth mode=%s region=%s", auth_mode, config.get("region"))
    client_kwargs = {"config": config}
    if signer is not None:
        client_kwargs["signer"] = signer
    return oci.object_storage.ObjectStorageClient(**client_kwargs)


def _create_os_client() -> oci.object_storage.ObjectStorageClient:
    global _OS_CLIENT, _OS_CLIENT_CTX
    ctx = _client_context()
    with _CLIENT_LOCK:
        if _OS_CLIENT is None or _OS_CLIENT_CTX != ctx:
            _OS_CLIENT = _build_os_client()
            _OS_CLIENT_CTX = ctx
    return _OS_CLIENT


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    try:
        return json.loads(json.dumps(obj, default=lambda o: getattr(o, "__dict__", str(o))))
    except Exception:
        return {"repr": repr(obj)}


def _norm_state(value: Any) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalpha())


def _group_state(state: Any) -> str:
    norm = _norm_state(state)
    if "SUCCEED" in norm:
        return "succeeded"
    if "FAILED" in norm:
        return "failed"
    if "CANCEL" in norm:
        return "canceled"
    if ("INPROGRESS" in norm) or ("ACCEPTED" in norm) or ("QUEUED" in norm):
        return "in_progress"
    return "other"


def _pick(job: dict[str, Any], key: str) -> Any:
    return job.get(key) or job.get(f"_{key}")


def _matches_bucket(job: dict[str, Any], bucket: str | None) -> bool:
    if not bucket:
        return True
    candidates: list[str] = []
    for section in ("output_location", "input_location", "outputLocation", "inputLocation"):
        value = job.get(section)
        if isinstance(value, dict):
            b = value.get("bucket_name") or value.get("_bucket_name") or value.get("bucketName")
            if b:
                candidates.append(str(b))
    if not candidates:
        return True
    bucket_l = bucket.lower()
    return any(bucket_l == c.lower() for c in candidates)


def create_transcription_job(
    compartment_id: str,
    namespace: str,
    bucket_name: str,
    file_names: List[str],
    job_name: str,
    model_type: str = "WHISPER_LARGE_V3T",
    language_code: str = "auto",
    whisper_prompt: Optional[str] = None,
    diarization_enabled: bool = True,
    output_prefix: str = "",
) -> Dict[str, Any]:
    speech_client = create_speech_client()

    model_key = str(model_type or "").strip().lower()
    mapped = MODEL_ALIAS_MAPPING.get(model_key)
    resolved_model_type = mapped.get("model_type") if mapped else model_type
    resolved_domain = mapped.get("domain") if mapped else "GENERIC"

    additional_settings: dict[str, Any] = {}
    if mapped and mapped.get("model_version"):
        additional_settings["modelVersion"] = mapped["model_version"]
    if whisper_prompt and resolved_model_type == "WHISPER_LARGE_V3T":
        additional_settings["whisperPrompt"] = whisper_prompt

    diarization = None
    if diarization_enabled is not None:
        diarization = oci.ai_speech.models.Diarization(is_diarization_enabled=bool(diarization_enabled))

    transcription_settings = oci.ai_speech.models.TranscriptionSettings(
        diarization=diarization,
        additional_settings=additional_settings or None,
    )

    model_details = oci.ai_speech.models.TranscriptionModelDetails(
        model_type=resolved_model_type,
        domain=resolved_domain,
        language_code=language_code,
        transcription_settings=transcription_settings,
    )

    object_location = oci.ai_speech.models.ObjectLocation(
        namespace_name=namespace,
        bucket_name=bucket_name,
        object_names=file_names,
    )

    input_location = oci.ai_speech.models.ObjectListInlineInputLocation(
        location_type="OBJECT_LIST_INLINE_INPUT_LOCATION",
        object_locations=[object_location],
    )

    output_location = oci.ai_speech.models.OutputLocation(
        namespace_name=namespace,
        bucket_name=bucket_name,
        prefix=output_prefix,
    )

    job_details = oci.ai_speech.models.CreateTranscriptionJobDetails(
        display_name=job_name,
        compartment_id=compartment_id,
        description="Speech transcription job created via MCP server",
        model_details=model_details,
        input_location=input_location,
        output_location=output_location,
    )

    response = speech_client.create_transcription_job(create_transcription_job_details=job_details)
    return {"job_id": response.data.id, "lifecycle_state": response.data.lifecycle_state}


def get_transcription_job(job_id: str):
    speech_client = create_speech_client()
    return speech_client.get_transcription_job(job_id).data


def list_transcription_jobs(compartment_id: str, **kwargs: Any):
    speech_client = create_speech_client()
    return speech_client.list_transcription_jobs(compartment_id=compartment_id, **kwargs).data


def list_transcription_tasks(transcription_job_id: str, **kwargs: Any):
    speech_client = create_speech_client()
    return speech_client.list_transcription_tasks(transcription_job_id=transcription_job_id, **kwargs).data


def _list_transcription_jobs_all(compartment_id: str, max_items: int = 1000, **kwargs: Any) -> list[Any]:
    speech_client = create_speech_client()
    items: list[Any] = []
    page: str | None = kwargs.pop("page", None)
    limit = kwargs.pop("limit", 100)
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 100

    while True:
        response = speech_client.list_transcription_jobs(compartment_id=compartment_id, page=page, limit=limit, **kwargs)
        data = response.data if hasattr(response, "data") else None
        page_items = getattr(data, "items", None) if data is not None else None
        if page_items:
            items.extend(page_items)
        if len(items) >= max_items:
            return items[:max_items]
        page = (getattr(response, "headers", None) or {}).get("opc-next-page")
        if not page:
            break
    return items


def _list_transcription_tasks_all(transcription_job_id: str, max_items: int = 200, **kwargs: Any) -> list[Any]:
    speech_client = create_speech_client()
    items: list[Any] = []
    page: str | None = kwargs.pop("page", None)
    limit = kwargs.pop("limit", 100)
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 100

    while True:
        response = speech_client.list_transcription_tasks(
            transcription_job_id=transcription_job_id,
            page=page,
            limit=limit,
            **kwargs,
        )
        data = response.data if hasattr(response, "data") else None
        page_items = getattr(data, "items", None) if data is not None else None
        if page_items:
            items.extend(page_items)
        if len(items) >= max_items:
            return items[:max_items]
        page = (getattr(response, "headers", None) or {}).get("opc-next-page")
        if not page:
            break
    return items


def _extract_input_object_names(input_location: Any) -> list[str]:
    raw = _to_dict(input_location)
    if not isinstance(raw, dict):
        return []

    names: list[str] = []
    object_locations = raw.get("object_locations") or raw.get("objectLocations")
    if isinstance(object_locations, list):
        for loc in object_locations:
            if not isinstance(loc, dict):
                continue
            obj_names = loc.get("object_names") or loc.get("objectNames")
            if isinstance(obj_names, list):
                names.extend([str(n) for n in obj_names if str(n).strip()])
    else:
        obj_names = raw.get("object_names") or raw.get("objectNames")
        if isinstance(obj_names, list):
            names.extend([str(n) for n in obj_names if str(n).strip()])

    return names


def _build_object_name_candidates(raw_object_name: str, default_prefix: str = "uploads/") -> list[str]:
    value = str(raw_object_name or "").strip()
    if not value:
        return []

    candidates: list[str] = [value]
    base_name = value.split("/")[-1].strip()
    if base_name and base_name not in candidates:
        candidates.append(base_name)
    if base_name:
        prefixed = f"{default_prefix.rstrip('/')}/{base_name}"
        if prefixed not in candidates:
            candidates.append(prefixed)
    if value.startswith("./"):
        alt = value[2:]
        if alt and alt not in candidates:
            candidates.append(alt)
    return candidates


def _match_input_name(query: str, object_name: str, default_prefix: str = "uploads/", allow_partial: bool = True) -> bool:
    q = str(query or "").strip()
    n = str(object_name or "").strip()
    if not q or not n:
        return False
    q_l = q.lower()
    n_l = n.lower()
    candidates = _build_object_name_candidates(q, default_prefix=default_prefix)
    for candidate in candidates:
        c_l = candidate.lower()
        if n_l == c_l:
            return True
        if n_l.endswith("/" + c_l):
            return True
    if allow_partial:
        base = n_l.split("/")[-1]
        if q_l in base or q_l in n_l:
            return True
    return False


def _fuzzy_score(query: str, candidate: str) -> int:
    q = str(query or "").strip().lower()
    c = str(candidate or "").strip().lower()
    if not q or not c:
        return 0
    if q == c:
        return 100
    if q in c:
        return 95
    c_base = c.split("/")[-1]
    if q in c_base:
        return 92
    ratio = SequenceMatcher(None, q, c).ratio()
    base_ratio = SequenceMatcher(None, q, c_base).ratio()
    return int(max(ratio, base_ratio) * 100)


def _list_bucket_audio_names(
    namespace: str,
    bucket: str,
    prefix: str,
    max_items: int,
    os_client: oci.object_storage.ObjectStorageClient | None = None,
) -> list[str]:
    if not os_client:
        os_client = _create_os_client()
    ext_set = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus", ".mp4", ".webm", ".mkv"}
    page: str | None = None
    names: list[str] = []
    while len(names) < max_items:
        response = os_client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket,
            prefix=prefix,
            fields="name,timeCreated,size",
            limit=min(1000, max_items - len(names)),
            page=page,
        )
        objects = getattr(response.data, "objects", None) or []
        if not objects:
            break
        for obj in objects:
            name = str(getattr(obj, "name", "") or "")
            if not name:
                continue
            low = name.lower()
            if any(low.endswith(ext) for ext in ext_set):
                names.append(name)
                if len(names) >= max_items:
                    break
        if len(names) >= max_items:
            break
        page = (getattr(response, "headers", None) or {}).get("opc-next-page")
        if not page:
            break
    return names


def _load_transcription_text_from_output_object(
    namespace: str,
    bucket: str,
    output_object_name: str,
    os_client: oci.object_storage.ObjectStorageClient | None = None,
) -> str:
    if not os_client:
        os_client = _create_os_client()
    response = os_client.get_object(namespace_name=namespace, bucket_name=bucket, object_name=output_object_name)
    raw = response.data.content if hasattr(response.data, "content") else response.data.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    parsed = json.loads(raw)
    transcriptions = parsed.get("transcriptions", []) if isinstance(parsed, dict) else []
    lines = [t.get("transcription", "") for t in transcriptions if isinstance(t, dict) and t.get("transcription", "")]
    return "\n\n".join(lines).strip()


def _verify_input_object_exists(namespace: str, bucket_name: str, object_name: str) -> dict[str, Any]:
    os_client = _create_os_client()
    response = os_client.head_object(
        namespace_name=namespace,
        bucket_name=bucket_name,
        object_name=object_name,
    )
    headers = dict(getattr(response, "headers", {}) or {})
    return {
        "content_length": headers.get("Content-Length") or headers.get("content-length"),
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "etag": headers.get("ETag") or headers.get("etag"),
    }


def _resolve_existing_input_object_name(namespace: str, bucket_name: str, requested_object_name: str) -> tuple[str, dict[str, Any]]:
    """
    Resolve the actual object key in bucket from a possibly short filename.
    Priority:
      1) exact key
      2) uploads/<basename>
      3) newest object ending with _<basename> (reference-style upload naming)
      4) newest object ending with /<basename>
    """
    os_client = _create_os_client()
    requested = str(requested_object_name or "").strip()
    if not requested:
        raise ValueError("requested_object_name is empty")

    candidates = [requested]
    base = requested.split("/")[-1].strip()
    if base:
        up = f"uploads/{base}"
        if up not in candidates:
            candidates.append(up)

    for cand in candidates:
        try:
            meta = _verify_input_object_exists(namespace=namespace, bucket_name=bucket_name, object_name=cand)
            return cand, meta
        except Exception:
            continue

    # Fallback scan for suffix matches (handles timestamped names like 174..._file.mp3)
    response = os_client.list_objects(
        namespace_name=namespace,
        bucket_name=bucket_name,
        fields="name,timeCreated,size",
        limit=1000,
    )
    objects = getattr(response.data, "objects", None) or []
    if not base:
        raise FileNotFoundError(f"No matching object found for '{requested}'")

    suffix_matches = []
    for obj in objects:
        name = str(getattr(obj, "name", "") or "")
        if not name:
            continue
        if name.endswith(f"_{base}") or name.endswith(f"/{base}") or name == base:
            suffix_matches.append(obj)

    if not suffix_matches:
        raise FileNotFoundError(f"No matching object found for '{requested}' (also checked basename '{base}')")

    suffix_matches.sort(key=lambda o: str(getattr(o, "time_created", "") or ""), reverse=True)
    selected = suffix_matches[0]
    selected_name = str(getattr(selected, "name", "") or "")
    meta = _verify_input_object_exists(namespace=namespace, bucket_name=bucket_name, object_name=selected_name)
    return selected_name, meta


def cancel_transcription_job(job_id: str) -> Dict[str, str]:
    speech_client = create_speech_client()
    speech_client.cancel_transcription_job(job_id)
    return {"status": "cancel_requested"}


def _get_latest_transcription_result(job_id: str, os_client: oci.object_storage.ObjectStorageClient | None = None) -> tuple[dict[str, Any], str, str, str, str]:
    job = get_transcription_job(job_id)
    lifecycle = str(getattr(job, "lifecycle_state", "") or "")
    if "SUCCEED" not in _norm_state(lifecycle):
        raise RuntimeError(f"Job {job_id} is in state '{lifecycle}', not SUCCEEDED.")

    output_loc = getattr(job, "output_location", None)
    namespace = getattr(output_loc, "namespace_name", None)
    bucket = getattr(output_loc, "bucket_name", None)
    prefix = getattr(output_loc, "prefix", "") or ""
    if not namespace or not bucket:
        raise RuntimeError("Could not resolve output namespace/bucket from job output_location.")

    if os_client is None:
        os_client = _create_os_client()

    input_loc = getattr(job, "input_location", None)
    object_names: list[str] = []
    if hasattr(input_loc, "object_locations") and input_loc.object_locations:
        for loc in input_loc.object_locations:
            if hasattr(loc, "object_names") and loc.object_names:
                object_names.extend(loc.object_names)

    candidates = [f"{prefix}{namespace}_{bucket}_{name}.json" for name in object_names if name]
    for object_name in candidates:
        try:
            get_resp = os_client.get_object(namespace_name=namespace, bucket_name=bucket, object_name=object_name)
            raw = get_resp.data.content if hasattr(get_resp.data, "content") else get_resp.data.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            data = json.loads(raw)
            return data, object_name, namespace, bucket, lifecycle
        except Exception:
            continue

    resp = os_client.list_objects(namespace_name=namespace, bucket_name=bucket, prefix=prefix)
    json_objs = [o for o in (resp.data.objects or []) if getattr(o, "name", "").lower().endswith(".json")]
    if not json_objs:
        raise FileNotFoundError(f"No transcription JSON found under prefix '{prefix}'")
    json_objs.sort(key=lambda o: (str(getattr(o, "time_created", "")), getattr(o, "size", 0)))
    selected = json_objs[-1]
    get_resp = os_client.get_object(namespace_name=namespace, bucket_name=bucket, object_name=selected.name)
    raw = get_resp.data.content if hasattr(get_resp.data, "content") else get_resp.data.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    data = json.loads(raw)
    return data, selected.name, namespace, bucket, lifecycle


def get_transcription_result_json(job_id: str) -> dict[str, Any]:
    result_json, _, _, _, _ = _get_latest_transcription_result(job_id)
    return result_json


def get_transcription_text(job_id: str) -> str:
    result_json, _, _, _, _ = _get_latest_transcription_result(job_id)
    transcriptions = result_json.get("transcriptions", []) if isinstance(result_json, dict) else []
    lines = [t.get("transcription", "") for t in transcriptions if isinstance(t, dict) and t.get("transcription", "")]
    return "\n\n".join(lines).strip()


async def _emit_progress(ctx: Any, progress: float, total: float = 100.0, message: str = "") -> None:
    if ctx is None:
        return
    report = getattr(ctx, "report_progress", None)
    if report is None:
        return
    try:
        maybe = report(progress=progress, total=total, message=message)
        if inspect.isawaitable(maybe):
            await maybe
    except Exception:
        logger.debug("tool=process_audio progress emit failed progress=%s total=%s", progress, total, exc_info=True)


async def handle_process_audio(payload: str | None = None, ctx: Any = None) -> str:
    logger.info("tool=process_audio start payload_present=%s", bool(payload))
    started_at = time.monotonic()
    await _emit_progress(ctx, 1, 100, "Starting process_audio")
    overrides: Dict[str, Any] = {}
    if payload:
        try:
            parsed = json.loads(payload)
            overrides = dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON payload", "hint": "Pass valid JSON string or omit payload."})

    defaults = _speech_defaults()
    compartment_id = _resolve_compartment_id(overrides)
    namespace = overrides.get("namespace") or defaults.get("namespace")
    bucket_name = overrides.get("bucket_name") or defaults.get("bucket_name")
    output_prefix = overrides.get("output_prefix") or defaults.get("output_prefix")
    model_type = overrides.get("model_type") or defaults.get("model_type") or "whisper-v3t"
    language_code = overrides.get("language_code") or defaults.get("language_code")
    whisper_prompt = None
    diarization_enabled = overrides.get("diarization_enabled")
    if diarization_enabled is None:
        diarization_enabled = defaults.get("diarization_enabled")

    poll_interval_seconds = overrides.get("poll_interval_seconds", 2)
    max_wait_seconds = overrides.get("max_wait_seconds", 300)
    try:
        poll_interval_seconds = max(1, min(int(poll_interval_seconds), 30))
    except Exception:
        poll_interval_seconds = 2
    try:
        max_wait_seconds = max(10, min(int(max_wait_seconds), 7200))
    except Exception:
        max_wait_seconds = 300

    object_name = str(overrides.get("object_name") or "").strip()
    file_names = overrides.get("file_names")
    if not object_name and isinstance(file_names, list):
        first = next((str(item).strip() for item in file_names if str(item).strip()), "")
        object_name = first
    if not object_name and isinstance(file_names, str):
        object_name = file_names.strip()

    uploaded_by_tool = False
    cleanup_input_object = bool(overrides.get("cleanup_input_object", False))
    cleanup_output_object = bool(overrides.get("cleanup_output_object", False))

    missing = [k for k, v in {"compartment_id": compartment_id, "namespace": namespace, "bucket_name": bucket_name, "language_code": language_code}.items() if not v]
    if not output_prefix:
        missing.append("output_prefix")

    if missing:
        logger.warning("tool=process_audio missing=%s", missing)
        return json.dumps({
            "error": "Missing required configuration",
            "missing": missing,
            "hint": "Provide required values in payload or environment.",
        })

    if not object_name:
        return json.dumps({
            "error": "Missing input audio object",
            "hint": "Provide payload.object_name (or file_names) for pre-uploaded object.",
        })

    try:
        resolved_object_name, object_meta = _resolve_existing_input_object_name(
            namespace=namespace,
            bucket_name=bucket_name,
            requested_object_name=object_name,
        )
        if resolved_object_name != object_name:
            logger.info(
                "tool=process_audio input_name_resolved requested=%s resolved=%s",
                object_name,
                resolved_object_name,
            )
            object_name = resolved_object_name
        logger.info(
            "tool=process_audio input_verified object=%s namespace=%s bucket=%s size=%s content_type=%s",
            object_name,
            namespace,
            bucket_name,
            object_meta.get("content_length"),
            object_meta.get("content_type"),
        )
    except Exception as exc:
        logger.exception(
            "tool=process_audio input_missing_or_inaccessible object=%s namespace=%s bucket=%s error=%s",
            object_name,
            namespace,
            bucket_name,
            exc,
        )
        return json.dumps({
            "status": "error",
            "error": f"Input object not accessible: {exc}",
            "input_object_name": object_name,
            "namespace": namespace,
            "bucket_name": bucket_name,
        })

    job_name = str(overrides.get("job_name") or "").strip() or f"transcription-{os.path.basename(object_name)}"
    speech_client = create_speech_client()
    job_id = ""
    lifecycle_state = ""
    result_object_name = ""
    transcription_text = ""

    try:
        submit_started = time.monotonic()
        logger.info(
            "tool=process_audio speech_config compartment=%s namespace=%s bucket=%s object=%s output_prefix=%s model_type=%s language_code=%s whisper_prompt=%s diarization=%s",
            str(compartment_id)[:24] + "...",
            namespace,
            bucket_name,
            object_name,
            output_prefix,
            model_type,
            language_code,
            bool(whisper_prompt),
            diarization_enabled,
        )
        await _emit_progress(ctx, 20, 100, "Submitting transcription job")
        result = create_transcription_job(
            compartment_id=compartment_id,
            namespace=namespace,
            bucket_name=bucket_name,
            file_names=[object_name],
            job_name=job_name,
            model_type=model_type,
            language_code=language_code,
            whisper_prompt=whisper_prompt,
            diarization_enabled=bool(diarization_enabled),
            output_prefix=output_prefix,
        )
        job_id = str(result.get("job_id") or "")
        logger.info("tool=process_audio submit_done job_id=%s submit_ms=%s", job_id, round((time.monotonic() - submit_started) * 1000))
        await _emit_progress(ctx, 30, 100, f"Job submitted: {job_id or 'pending'}")
        deadline = time.monotonic() + max_wait_seconds
        poll_count = 0
        poll_started = time.monotonic()

        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Transcription job {job_id} exceeded {max_wait_seconds} seconds")

            job = speech_client.get_transcription_job(job_id).data
            lifecycle_state = str(getattr(job, "lifecycle_state", "") or "")
            logger.info("tool=process_audio poll job_id=%s state=%s", job_id, lifecycle_state)
            poll_count += 1
            progress_value = min(90.0, 35.0 + (poll_count * 4.0))
            await _emit_progress(ctx, progress_value, 100, f"Job state: {lifecycle_state}")

            norm = _norm_state(lifecycle_state)
            if "SUCCEED" in norm:
                break
            if "FAILED" in norm or "CANCEL" in norm:
                raise RuntimeError(f"Transcription job {job_id} ended in state {lifecycle_state}")
            time.sleep(poll_interval_seconds)

        logger.info(
            "tool=process_audio poll_done job_id=%s poll_count=%s poll_ms=%s final_state=%s",
            job_id,
            poll_count,
            round((time.monotonic() - poll_started) * 1000),
            lifecycle_state,
        )

        await _emit_progress(ctx, 95, 100, "Fetching transcript")
        fetch_started = time.monotonic()
        result_json, result_object_name, resolved_namespace, resolved_bucket, lifecycle_state = _get_latest_transcription_result(job_id)
        transcriptions = result_json.get("transcriptions", []) if isinstance(result_json, dict) else []
        lines = [t.get("transcription", "") for t in transcriptions if isinstance(t, dict) and t.get("transcription", "")]
        transcription_text = "\n\n".join(lines).strip()
        logger.info(
            "tool=process_audio fetch_done job_id=%s fetch_ms=%s transcript_len=%s total_ms=%s",
            job_id,
            round((time.monotonic() - fetch_started) * 1000),
            len(transcription_text),
            round((time.monotonic() - started_at) * 1000),
        )
        await _emit_progress(ctx, 100, 100, "process_audio completed")

        return json.dumps({
            "status": "success",
            "job_id": job_id,
            "lifecycle_state": lifecycle_state,
            "namespace_name": resolved_namespace,
            "bucket_name": resolved_bucket,
            "input_object_name": object_name,
            "result_object_name": result_object_name,
            "transcription_text": transcription_text,
            "uploaded_by_tool": uploaded_by_tool,
            "cleanup_input_object": cleanup_input_object,
            "cleanup_output_object": cleanup_output_object,
        })
    except Exception as exc:
        logger.exception("tool=process_audio failed job_id=%s error=%s", job_id, exc)
        return json.dumps({
            "status": "error",
            "error": str(exc),
            "job_id": job_id or None,
            "input_object_name": object_name,
        })
    finally:
        os_client = _create_os_client()
        if cleanup_input_object and object_name:
            try:
                os_client.delete_object(namespace_name=namespace, bucket_name=bucket_name, object_name=object_name)
            except Exception:
                logger.warning("tool=process_audio cleanup failed for input object=%s", object_name, exc_info=True)
        if cleanup_output_object and result_object_name:
            try:
                os_client.delete_object(namespace_name=namespace, bucket_name=bucket_name, object_name=result_object_name)
            except Exception:
                logger.warning("tool=process_audio cleanup failed for result object=%s", result_object_name, exc_info=True)


def handle_create_speech_transcription_job(payload: str | None = None) -> str:
    logger.info("tool=create_speech_transcription_job start payload_present=%s", bool(payload))

    overrides: Dict[str, Any] = {}
    if payload:
        try:
            parsed = json.loads(payload)
            overrides = dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON payload", "hint": "Pass valid JSON string or omit payload."})

    defaults = _speech_defaults()
    compartment_id = _resolve_compartment_id(overrides)
    namespace = overrides.get("namespace") or defaults.get("namespace")
    bucket_name = overrides.get("bucket_name") or defaults.get("bucket_name")
    file_names = overrides.get("file_names")
    if isinstance(file_names, str):
        file_names = [file_names.strip()]
    file_names = [str(name).strip() for name in (file_names or []) if str(name).strip()]

    job_name = overrides.get("job_name") or defaults.get("job_name")
    model_type = overrides.get("model_type") or defaults.get("model_type") or "whisper-v3t"
    language_code = overrides.get("language_code") or defaults.get("language_code")
    whisper_prompt = None
    diarization_enabled = overrides.get("diarization_enabled")
    if diarization_enabled is None:
        diarization_enabled = defaults.get("diarization_enabled")
    output_prefix = overrides.get("output_prefix") or defaults.get("output_prefix")

    missing = [k for k, v in {"compartment_id": compartment_id, "namespace": namespace, "bucket_name": bucket_name, "language_code": language_code}.items() if not v]
    if not file_names:
        missing.append("file_names")
    if not job_name:
        missing.append("job_name")
    if not output_prefix:
        missing.append("output_prefix")
    if missing:
        logger.warning("tool=create_speech_transcription_job missing=%s", missing)
        return json.dumps(
            {
                "error": "Missing required configuration",
                "missing": missing,
                "hint": "Provide all required fields in payload: compartment_id, namespace, bucket_name, file_names, job_name, output_prefix.",
            }
        )

    try:
        logger.info(
            "tool=create_speech_transcription_job effective compartment=%s namespace=%s bucket=%s model=%s lang=%s files=%s",
            str(compartment_id)[:24] + "...",
            namespace,
            bucket_name,
            model_type,
            language_code,
            len(file_names) if isinstance(file_names, list) else 0,
        )
        result = create_transcription_job(
            compartment_id=compartment_id,
            namespace=namespace,
            bucket_name=bucket_name,
            file_names=file_names,
            job_name=job_name,
            model_type=model_type,
            language_code=language_code,
            whisper_prompt=whisper_prompt,
            diarization_enabled=bool(diarization_enabled),
            output_prefix=output_prefix,
        )
        logger.info("tool=create_speech_transcription_job success job_id=%s file_count=%s", result.get("job_id"), len(file_names))
        return json.dumps({
            "status": "submitted",
            "job": result,
            "params": {
                "compartment_id": compartment_id,
                "namespace": namespace,
                "bucket_name": bucket_name,
                "file_names": file_names,
                "job_name": job_name,
                "model_type": model_type,
                "language_code": language_code,
                "diarization_enabled": bool(diarization_enabled),
                "output_prefix": output_prefix,
            },
        })
    except Exception as exc:
        logger.exception("tool=create_speech_transcription_job failed error=%s", exc)
        return json.dumps({"error": str(exc)})


def handle_get_speech_transcription_job(job_id: str) -> str:
    logger.info("tool=get_speech_transcription_job start job_id=%s", job_id)
    try:
        job = get_transcription_job(job_id)
        job_dict = _to_dict(job)
        lifecycle = getattr(job, "lifecycle_state", None) or (_pick(job_dict, "lifecycle_state") if isinstance(job_dict, dict) else None)

        tasks_payload: list[dict[str, Any]] = []
        tasks_summary: dict[str, Any] = {"count": 0, "counts_by_state": {}}
        try:
            tasks_result = list_transcription_tasks(job_id, limit=100)
            raw_tasks = tasks_result if isinstance(tasks_result, list) else getattr(tasks_result, "items", [])
            state_counts: dict[str, int] = {}
            for t in raw_tasks or []:
                td = _to_dict(t)
                if not isinstance(td, dict):
                    continue
                task_state = _pick(td, "lifecycle_state") or td.get("lifecycleState") or ""
                grp = _group_state(task_state)
                state_counts[grp] = state_counts.get(grp, 0) + 1
                tasks_payload.append({
                    "task_id": _pick(td, "id") or td.get("id"),
                    "display_name": _pick(td, "display_name") or td.get("displayName"),
                    "lifecycle_state": task_state,
                })
            tasks_summary = {"count": len(tasks_payload), "counts_by_state": state_counts}
        except Exception as tasks_exc:
            tasks_summary = {"count": 0, "error": str(tasks_exc)}

        logger.info("tool=get_speech_transcription_job success job_id=%s lifecycle=%s", job_id, lifecycle)
        return json.dumps({
            "job_id": job_id,
            "lifecycle_state": lifecycle,
            "status": lifecycle,
            "job": job_dict,
            "tasks_summary": tasks_summary,
            "tasks": tasks_payload,
        })
    except Exception as exc:
        logger.exception("tool=get_speech_transcription_job failed job_id=%s error=%s", job_id, exc)
        return json.dumps({"error": str(exc), "job_id": job_id})


def handle_list_speech_transcription_jobs(payload: str | None = None) -> str:
    logger.info("tool=list_speech_transcription_jobs start payload_present=%s", bool(payload))
    overrides: Dict[str, Any] = {}
    if payload:
        try:
            overrides = json.loads(payload)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON payload"})

    compartment_id = _resolve_compartment_id(overrides)
    bucket_name = overrides.get("bucket_name")
    response_mode = str(overrides.get("response_mode") or "compact").strip().lower()
    if response_mode not in {"compact", "full"}:
        response_mode = "compact"
    limit = overrides.get("limit", 50)
    try:
        limit = max(1, min(int(limit), 200))
    except Exception:
        limit = 50

    if not compartment_id:
        logger.warning("tool=list_speech_transcription_jobs missing compartment_id")
        return json.dumps({
            "error": "Missing required inputs",
            "missing": ["compartment_id"],
            "hint": "Provide compartment_id in payload.",
        })

    try:
        list_kwargs: Dict[str, Any] = {"limit": limit}
        for key in ("lifecycle_state", "display_name", "id", "page", "sort_order", "sort_by"):
            value = overrides.get(key)
            if value not in (None, ""):
                list_kwargs[key] = value

        result = list_transcription_jobs(compartment_id, **list_kwargs)
        jobs = [_to_dict(j) for j in (result if isinstance(result, list) else getattr(result, "items", [result]))]
        jobs = [j for j in jobs if isinstance(j, dict) and _matches_bucket(j, bucket_name)]

        normalized = [{
            "job_id": _pick(j, "id") or _pick(j, "job_id") or "",
            "display_name": _pick(j, "display_name") or "",
            "lifecycle_state": _pick(j, "lifecycle_state") or "",
            "time_accepted": str(_pick(j, "time_accepted") or ""),
            "time_started": str(_pick(j, "time_started") or ""),
            "time_finished": str(_pick(j, "time_finished") or ""),
        } for j in jobs]
        normalized.sort(key=lambda j: (j.get("time_accepted") or j.get("time_started") or j.get("time_finished") or ""), reverse=True)
        normalized = normalized[:limit]

        by_state = {
            "succeeded": [j for j in normalized if _group_state(j.get("lifecycle_state")) == "succeeded"],
            "failed": [j for j in normalized if _group_state(j.get("lifecycle_state")) == "failed"],
            "canceled": [j for j in normalized if _group_state(j.get("lifecycle_state")) == "canceled"],
            "in_progress": [j for j in normalized if _group_state(j.get("lifecycle_state")) == "in_progress"],
            "other": [j for j in normalized if _group_state(j.get("lifecycle_state")) == "other"],
        }

        if response_mode == "full":
            logger.info("tool=list_speech_transcription_jobs success mode=full count=%s", len(normalized))
            return json.dumps({
                "response_mode_effective": "full",
                "compartment_id": compartment_id,
                "bucket_filter": bucket_name,
                "filters": {"lifecycle_state": overrides.get("lifecycle_state")},
                "count": len(normalized),
                "counts_by_state": {k: len(v) for k, v in by_state.items()},
                "by_state": by_state,
                "jobs": normalized,
            })

        compact_jobs = [{"job_id": j.get("job_id"), "display_name": j.get("display_name"), "status": j.get("lifecycle_state")} for j in normalized]
        next_action = "create_job"
        if by_state["in_progress"]:
            next_action = "poll_job_status"
        elif by_state["succeeded"]:
            next_action = "read_transcription_result"
        elif by_state["failed"]:
            next_action = "inspect_failed_job_or_resubmit"

        logger.info("tool=list_speech_transcription_jobs success mode=compact count=%s", len(compact_jobs))
        return json.dumps({
            "response_mode_effective": "compact",
            "scope": {"compartment_id": compartment_id, "bucket_name": bucket_name},
            "summary": {
                "total": len(compact_jobs),
                "counts_by_state": {k: len(v) for k, v in by_state.items()},
                "next_action": next_action,
                "latest_job_id": compact_jobs[0]["job_id"] if compact_jobs else None,
            },
            "jobs": compact_jobs,
        })
    except Exception as exc:
        logger.exception("tool=list_speech_transcription_jobs failed error=%s", exc)
        return json.dumps({"error": str(exc)})


def handle_cancel_speech_transcription_job(job_id: str) -> str:
    logger.info("tool=cancel_speech_transcription_job start job_id=%s", job_id)
    try:
        job = get_transcription_job(job_id)
        state = str(getattr(job, "lifecycle_state", "") or "")
        norm = _norm_state(state)
        if not (("ACCEPTED" in norm) or ("INPROGRESS" in norm)):
            logger.info("tool=cancel_speech_transcription_job skipped job_id=%s state=%s", job_id, state)
            return json.dumps({"job_id": job_id, "status": "skipped", "lifecycle_state": state})
        result = cancel_transcription_job(job_id)
        logger.info("tool=cancel_speech_transcription_job requested job_id=%s", job_id)
        return json.dumps({"job_id": job_id, "lifecycle_state": state, "status": "cancel_requested", **(result if isinstance(result, dict) else {"result": result})})
    except Exception as exc:
        logger.exception("tool=cancel_speech_transcription_job failed job_id=%s error=%s", job_id, exc)
        return json.dumps({"error": str(exc), "job_id": job_id})


def handle_get_speech_transcription_text(job_id: str) -> str:
    logger.info("tool=get_speech_transcription_text start job_id=%s", job_id)
    try:
        job = get_transcription_job(job_id)
        lifecycle = str(getattr(job, "lifecycle_state", "") or "")
        if "SUCCEED" not in _norm_state(lifecycle):
            logger.info("tool=get_speech_transcription_text skipped job_id=%s state=%s", job_id, lifecycle)
            return json.dumps({"job_id": job_id, "status": "error", "lifecycle_state": lifecycle, "error": "Job is not in SUCCEEDED state"})

        result_json = get_transcription_result_json(job_id)
        transcriptions = result_json.get("transcriptions", []) if isinstance(result_json, dict) else []
        lines = [t.get("transcription", "") for t in transcriptions if isinstance(t, dict) and t.get("transcription", "")]
        transcription_text = "\n\n".join(lines).strip()
        if not transcription_text:
            transcription_text = get_transcription_text(job_id)

        logger.info("tool=get_speech_transcription_text success job_id=%s text_len=%s", job_id, len(transcription_text))
        return json.dumps({
            "job_id": job_id,
            "status": "success",
            "lifecycle_state": lifecycle,
            "transcription_text": transcription_text,
        })
    except Exception as exc:
        logger.exception("tool=get_speech_transcription_text failed job_id=%s error=%s", job_id, exc)
        return json.dumps({"job_id": job_id, "status": "error", "error": str(exc)})


def handle_read_transcription_result(job_id: str) -> str:
    logger.info("tool=read_transcription_result start job_id=%s", job_id)
    try:
        os_client = _create_os_client()
        data, result_object_name, namespace, bucket, lifecycle = _get_latest_transcription_result(job_id, os_client=os_client)
        transcriptions = data.get("transcriptions", [])

        full_texts = [tx.get("transcription", "") for tx in transcriptions if isinstance(tx, dict) and tx.get("transcription", "")]
        transcription_text = "\n\n".join(full_texts).strip()

        speaker_stats: dict[str, dict[str, Any]] = {}
        # speaker_segments: list[dict[str, Any]] = []
        # for tx in transcriptions:
        #     if not isinstance(tx, dict):
        #         continue
        #     for tok in tx.get("tokens", []) or []:
        #         if not isinstance(tok, dict):
        #             continue
        #         speaker = tok.get("speakerIndex")
        #         if speaker is None:
        #             speaker = tok.get("speaker")
        #         if speaker is None:
        #             continue
        #         key = str(speaker)
        #         token_text = str(tok.get("token") or "")
        #         start_time = str(tok.get("startTime") or "")
        #         end_time = str(tok.get("endTime") or "")
        #         speaker_segments.append({"speaker": key, "text": token_text, "start_time": start_time, "end_time": end_time})
        #         entry = speaker_stats.setdefault(key, {"speaker": key, "token_count": 0, "start_time": "", "end_time": ""})
        #         entry["token_count"] += 1
        #         if start_time and (not entry["start_time"] or start_time < entry["start_time"]):
        #             entry["start_time"] = start_time
        #         if end_time and (not entry["end_time"] or end_time > entry["end_time"]):
        #             entry["end_time"] = end_time

        speaker_details = sorted(speaker_stats.values(), key=lambda x: x.get("speaker", ""))
        logger.info("tool=read_transcription_result success job_id=%s object=%s text_len=%s", job_id, result_object_name, len(transcription_text))
        return json.dumps({
            "job_id": job_id,
            "status": "success",
            "lifecycle_state": lifecycle,
            "namespace_name": namespace,
            "bucket_name": bucket,
            "result_object_name": result_object_name,
            "transcription_text": transcription_text,
            "speaker_details": speaker_details,
            # "speaker_segments": speaker_segments[:400],
        })
    except Exception as exc:
        logger.exception("tool=read_transcription_result failed job_id=%s error=%s", job_id, exc)
        return json.dumps({"error": str(exc), "job_id": job_id})


def handle_list_bucket_audio_files(payload: str | None = None) -> str:
    logger.info("tool=list_bucket_audio_files start payload_present=%s", bool(payload))
    overrides: Dict[str, Any] = {}
    if payload:
        try:
            parsed = json.loads(payload)
            overrides = dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON payload"})

    defaults = _speech_defaults()
    namespace = overrides.get("namespace") or defaults.get("namespace")
    bucket = overrides.get("bucket_name") or defaults.get("bucket_name")
    defaults = _speech_defaults()
    prefix = overrides.get("prefix", defaults.get("input_prefix") or "uploads/")
    compartment_id = _resolve_compartment_id(overrides)
    include_job_links = bool(overrides.get("include_job_links", True))
    max_job_scan = overrides.get("max_job_scan", 1000)
    try:
        max_job_scan = max(1, min(int(max_job_scan), 5000))
    except Exception:
        max_job_scan = 1000
    limit = overrides.get("limit", 1000)
    try:
        limit = max(1, min(int(limit), 5000))
    except Exception:
        limit = 1000

    missing = [k for k, v in {"namespace": namespace, "bucket_name": bucket}.items() if not v]
    if include_job_links and not compartment_id:
        missing.append("compartment_id")
    if missing:
        logger.warning("tool=list_bucket_audio_files missing=%s", missing)
        return json.dumps({
            "error": "Missing required inputs",
            "missing": missing,
            "hint": "Provide required values in payload. compartment_id is required when include_job_links=true.",
        })

    try:
        os_client = _create_os_client()
        resp = os_client.list_objects(namespace_name=namespace, bucket_name=bucket, prefix=prefix, fields="name,timeCreated,size")
        audio_exts = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
        files = []
        for obj in (resp.data.objects or []):
            name = getattr(obj, "name", "")
            if any(name.lower().endswith(ext) for ext in audio_exts):
                files.append({"name": name, "size_kb": round(getattr(obj, "size", 0) / 1024, 1), "created": str(getattr(obj, "time_created", "")), "related_jobs": []})
        files.sort(key=lambda x: x.get("created", ""), reverse=True)
        files = files[:limit]

        file_index = {f.get("name", ""): f for f in files if f.get("name")}
        if include_job_links and compartment_id and file_index:
            try:
                raw_jobs = _list_transcription_jobs_all(compartment_id, max_items=max_job_scan, limit=100)
                for j in raw_jobs or []:
                    jd = _to_dict(j)
                    if not isinstance(jd, dict):
                        continue
                    job_id = _pick(jd, "id") or _pick(jd, "job_id") or ""
                    lifecycle_state = _pick(jd, "lifecycle_state") or jd.get("lifecycleState") or ""
                    out_loc = jd.get("output_location") or jd.get("outputLocation") or {}
                    out_ns = out_loc.get("namespace_name") or out_loc.get("namespaceName")
                    out_bucket = out_loc.get("bucket_name") or out_loc.get("bucketName")
                    out_prefix = out_loc.get("prefix") or ""
                    in_loc = jd.get("input_location") or jd.get("inputLocation") or {}
                    obj_locs = in_loc.get("object_locations") or in_loc.get("objectLocations") or []
                    if not isinstance(obj_locs, list):
                        continue
                    for loc in obj_locs:
                        if not isinstance(loc, dict):
                            continue
                        obj_names = loc.get("object_names") or loc.get("objectNames") or []
                        if not isinstance(obj_names, list):
                            continue
                        for obj_name in obj_names:
                            if obj_name not in file_index:
                                continue
                            result_object_name = None
                            if out_ns and out_bucket and out_prefix and out_ns == namespace and out_bucket == bucket:
                                result_object_name = f"{out_prefix}{out_ns}_{out_bucket}_{obj_name}.json"
                            file_index[obj_name]["related_jobs"].append({
                                "job_id": job_id,
                                "status": lifecycle_state,
                                "result_object_name": result_object_name,
                            })
            except Exception as link_exc:
                logger.warning("tool=list_bucket_audio_files enrichment_failed error=%s", link_exc)

        logger.info("tool=list_bucket_audio_files success namespace=%s bucket=%s count=%s", namespace, bucket, len(files))
        return json.dumps({
            "namespace": namespace,
            "bucket": bucket,
            "prefix": prefix,
            "count": len(files),
            "include_job_links": include_job_links,
            "max_job_scan": max_job_scan,
            "files": files,
        })
    except Exception as exc:
        logger.exception("tool=list_bucket_audio_files failed error=%s", exc)
        return json.dumps({"error": str(exc)})


def handle_find_transcription_job_by_object(payload: str | None = None) -> str:
    logger.info("tool=find_transcription_job_by_object start payload_present=%s", bool(payload))
    overrides: Dict[str, Any] = {}
    if payload:
        try:
            parsed = json.loads(payload)
            overrides = dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON payload"})

    defaults = _speech_defaults()
    object_name = str(overrides.get("object_name") or "").strip()
    namespace = str(overrides.get("namespace") or defaults.get("namespace") or "").strip()
    bucket = str(overrides.get("bucket_name") or defaults.get("bucket_name") or "").strip()
    compartment_id = _resolve_compartment_id(overrides)
    lifecycle_state = str(overrides.get("lifecycle_state") or "").strip().upper()
    include_transcription_text = bool(overrides.get("include_transcription_text", False))
    default_prefix = str(overrides.get("default_prefix") or defaults.get("input_prefix") or "uploads/").strip() or "uploads/"
    output_prefix = str(overrides.get("output_prefix") or defaults.get("output_prefix") or "").strip()
    allow_partial_name_match = bool(overrides.get("allow_partial_name_match", True))
    include_debug = bool(overrides.get("include_debug", False))
    enable_fuzzy_fallback = bool(overrides.get("enable_fuzzy_fallback", True))
    fuzzy_threshold = overrides.get("fuzzy_threshold", 70)
    fuzzy_max_candidates = overrides.get("fuzzy_max_candidates", 10)
    fuzzy_scan_limit = overrides.get("fuzzy_scan_limit", 2000)
    max_job_scan = overrides.get("max_job_scan", 1000)
    try:
        max_job_scan = max(1, min(int(max_job_scan), 5000))
    except Exception:
        max_job_scan = 1000
    try:
        fuzzy_threshold = max(1, min(int(fuzzy_threshold), 100))
    except Exception:
        fuzzy_threshold = 70
    try:
        fuzzy_max_candidates = max(1, min(int(fuzzy_max_candidates), 30))
    except Exception:
        fuzzy_max_candidates = 10
    try:
        fuzzy_scan_limit = max(100, min(int(fuzzy_scan_limit), 10000))
    except Exception:
        fuzzy_scan_limit = 2000

    missing = [k for k, v in {"object_name": object_name, "compartment_id": compartment_id, "namespace": namespace, "bucket_name": bucket, "output_prefix": output_prefix}.items() if not v]
    if missing:
        return json.dumps({
            "error": "Missing required inputs",
            "missing": missing,
            "hint": "Provide required fields in payload: object_name, compartment_id, namespace, bucket_name, output_prefix.",
        })

    object_candidates = _build_object_name_candidates(object_name, default_prefix=default_prefix)
    lifecycle_for_api = lifecycle_state
    if lifecycle_for_api in {"", "ALL", "*", "ANY"}:
        lifecycle_for_api = ""

    try:
        list_kwargs: dict[str, Any] = {
            "limit": 100,
            "sort_by": "timeCreated",
            "sort_order": "DESC",
        }
        if lifecycle_for_api:
            list_kwargs["lifecycle_state"] = lifecycle_for_api

        jobs = _list_transcription_jobs_all(
            compartment_id=compartment_id,
            max_items=max_job_scan,
            **list_kwargs,
        )
        os_client = _create_os_client() if include_transcription_text else None
        matches: list[dict[str, Any]] = []
        seen_input_names: set[str] = set()
        scanned_job_inputs: list[dict[str, Any]] = []
        bucket_match_count = 0
        fuzzy_candidates: list[dict[str, Any]] = []

        for job in jobs:
            jd = _to_dict(job)
            if not isinstance(jd, dict):
                continue
            job_id_for_debug = _pick(jd, "id") or _pick(jd, "job_id") or ""
            lifecycle_for_debug = _pick(jd, "lifecycle_state") or jd.get("lifecycleState") or ""
            bucket_match = _matches_bucket(jd, bucket or None)
            input_location = jd.get("input_location") or jd.get("inputLocation")
            input_object_names = _extract_input_object_names(input_location)
            # Some list APIs omit inline input object names; enrich via get by job_id when empty.
            if not input_object_names and job_id_for_debug:
                try:
                    full_job = get_transcription_job(job_id_for_debug)
                    full_job_dict = _to_dict(full_job)
                    if isinstance(full_job_dict, dict):
                        full_input = full_job_dict.get("input_location") or full_job_dict.get("inputLocation")
                        full_names = _extract_input_object_names(full_input)
                        if full_names:
                            input_object_names = full_names
                except Exception:
                    pass
            for name in input_object_names:
                seen_input_names.add(str(name))
            scanned_job_inputs.append({
                "job_id": job_id_for_debug,
                "lifecycle_state": lifecycle_for_debug,
                "bucket_match": bucket_match,
                "input_object_names": input_object_names[:10],
            })
            if not bucket_match:
                continue
            bucket_match_count += 1
            if not any(_match_input_name(object_name, n, default_prefix=default_prefix, allow_partial=allow_partial_name_match) for n in input_object_names):
                continue

            job_id = job_id_for_debug
            entry = {
                "job_id": job_id,
                "display_name": _pick(jd, "display_name") or jd.get("displayName"),
                "lifecycle_state": lifecycle_for_debug,
                "time_accepted": str(_pick(jd, "time_accepted") or jd.get("timeAccepted") or ""),
                "time_finished": str(_pick(jd, "time_finished") or jd.get("timeFinished") or ""),
                "input_object_name": object_name,
                "task_id": None,
                "task_lifecycle_state": None,
                "result_object_name": None,
            }

            try:
                tasks = _list_transcription_tasks_all(job_id, max_items=200, sort_by="timeCreated", sort_order="DESC")
            except Exception:
                tasks = []

            for task in tasks:
                td = _to_dict(task)
                if not isinstance(td, dict):
                    continue
                task_input = td.get("input_location") or td.get("inputLocation")
                task_input_names = _extract_input_object_names(task_input)
                if not any(_match_input_name(object_name, n, default_prefix=default_prefix, allow_partial=allow_partial_name_match) for n in task_input_names):
                    continue
                task_output = td.get("output_location") or td.get("outputLocation") or {}
                output_names = _extract_input_object_names(task_output)
                entry["task_id"] = _pick(td, "id") or td.get("id")
                entry["task_lifecycle_state"] = _pick(td, "lifecycle_state") or td.get("lifecycleState")
                entry["result_object_name"] = output_names[0] if output_names else None
                break

            if include_transcription_text and entry.get("result_object_name") and namespace and bucket:
                try:
                    entry["transcription_text"] = _load_transcription_text_from_output_object(
                        namespace=namespace,
                        bucket=bucket,
                        output_object_name=str(entry["result_object_name"]),
                        os_client=os_client,
                    )
                except Exception:
                    entry["transcription_text"] = None
            elif include_transcription_text and "SUCCEED" in _norm_state(entry.get("lifecycle_state")) and job_id:
                try:
                    entry["transcription_text"] = get_transcription_text(job_id)
                except Exception:
                    entry["transcription_text"] = None

            matches.append(entry)

        # Fallback: when input-location matching finds nothing, resolve via output objects under SPEECH_OUTPUT_PREFIX.
        if not matches and namespace and bucket and output_prefix:
            os_client_for_fallback = os_client or _create_os_client()
            try:
                objects_resp = os_client_for_fallback.list_objects(
                    namespace_name=namespace,
                    bucket_name=bucket,
                    prefix=output_prefix,
                    fields="name,timeCreated",
                )
                output_objects = []
                for obj in (objects_resp.data.objects or []):
                    name = str(getattr(obj, "name", "") or "")
                    if not name.lower().endswith(".json"):
                        continue
                    target_name = name[:-5]  # strip .json
                    if _match_input_name(object_name, target_name, default_prefix=default_prefix, allow_partial=allow_partial_name_match):
                        output_objects.append(name)

                for out_obj_name in output_objects:
                    # Fast path: derive job token from output path (SpeechJobOutput/job-<token>/...)
                    # and map to job OCID suffix token.
                    matched_direct = False
                    for job in jobs:
                        jd = _to_dict(job)
                        if not isinstance(jd, dict):
                            continue
                        if not _matches_bucket(jd, bucket or None):
                            continue
                        job_id = _pick(jd, "id") or _pick(jd, "job_id") or ""
                        if not job_id:
                            continue
                        job_token = str(job_id).split(".")[-1]
                        if f"/job-{job_token}/" not in out_obj_name:
                            continue
                        lifecycle = _pick(jd, "lifecycle_state") or jd.get("lifecycleState")
                        entry = {
                            "job_id": job_id,
                            "display_name": _pick(jd, "display_name") or jd.get("displayName"),
                            "lifecycle_state": lifecycle,
                            "time_accepted": str(_pick(jd, "time_accepted") or jd.get("timeAccepted") or ""),
                            "time_finished": str(_pick(jd, "time_finished") or jd.get("timeFinished") or ""),
                            "input_object_name": object_name,
                            "task_id": None,
                            "task_lifecycle_state": None,
                            "result_object_name": out_obj_name,
                            "matched_via": "output_object_job_token",
                        }
                        if include_transcription_text:
                            try:
                                entry["transcription_text"] = _load_transcription_text_from_output_object(
                                    namespace=namespace,
                                    bucket=bucket,
                                    output_object_name=out_obj_name,
                                    os_client=os_client_for_fallback,
                                )
                            except Exception:
                                entry["transcription_text"] = None
                        matches.append(entry)
                        matched_direct = True
                        break
                    if matched_direct:
                        continue

                    for job in jobs:
                        jd = _to_dict(job)
                        if not isinstance(jd, dict):
                            continue
                        if not _matches_bucket(jd, bucket or None):
                            continue
                        job_id = _pick(jd, "id") or _pick(jd, "job_id") or ""
                        if not job_id:
                            continue
                        try:
                            tasks = _list_transcription_tasks_all(job_id, max_items=200, sort_by="timeCreated", sort_order="DESC")
                        except Exception:
                            tasks = []
                        matched_task = None
                        for task in tasks:
                            td = _to_dict(task)
                            if not isinstance(td, dict):
                                continue
                            task_output = td.get("output_location") or td.get("outputLocation") or {}
                            output_names = _extract_input_object_names(task_output)
                            if out_obj_name in output_names:
                                matched_task = td
                                break
                        if not matched_task:
                            continue

                        lifecycle = _pick(jd, "lifecycle_state") or jd.get("lifecycleState")
                        entry = {
                            "job_id": job_id,
                            "display_name": _pick(jd, "display_name") or jd.get("displayName"),
                            "lifecycle_state": lifecycle,
                            "time_accepted": str(_pick(jd, "time_accepted") or jd.get("timeAccepted") or ""),
                            "time_finished": str(_pick(jd, "time_finished") or jd.get("timeFinished") or ""),
                            "input_object_name": object_name,
                            "task_id": _pick(matched_task, "id") or matched_task.get("id"),
                            "task_lifecycle_state": _pick(matched_task, "lifecycle_state") or matched_task.get("lifecycleState"),
                            "result_object_name": out_obj_name,
                            "matched_via": "output_object_fallback",
                        }
                        if include_transcription_text:
                            try:
                                entry["transcription_text"] = _load_transcription_text_from_output_object(
                                    namespace=namespace,
                                    bucket=bucket,
                                    output_object_name=out_obj_name,
                                    os_client=os_client_for_fallback,
                                )
                            except Exception:
                                entry["transcription_text"] = None
                        matches.append(entry)
                        break
            except Exception:
                pass

        # Fuzzy fallback: score bucket object names and try matching candidates to jobs.
        if (
            not matches
            and enable_fuzzy_fallback
            and namespace
            and bucket
            and len(object_name) >= 3
        ):
            os_client_for_fuzzy = os_client or _create_os_client()
            fuzzy_prefix = default_prefix if default_prefix.endswith("/") else f"{default_prefix}/"
            try:
                all_audio_names = _list_bucket_audio_names(
                    namespace=namespace,
                    bucket=bucket,
                    prefix=fuzzy_prefix,
                    max_items=fuzzy_scan_limit,
                    os_client=os_client_for_fuzzy,
                )
                scored = [
                    {"name": name, "score": _fuzzy_score(object_name, name)}
                    for name in all_audio_names
                ]
                scored = [item for item in scored if int(item.get("score") or 0) >= fuzzy_threshold]
                scored.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("name") or "")), reverse=True)
                fuzzy_candidates = scored[:fuzzy_max_candidates]

                for cand in fuzzy_candidates:
                    cand_name = str(cand.get("name") or "").strip()
                    cand_score = int(cand.get("score") or 0)
                    if not cand_name:
                        continue
                    for job in jobs:
                        jd = _to_dict(job)
                        if not isinstance(jd, dict):
                            continue
                        if not _matches_bucket(jd, bucket or None):
                            continue
                        job_id = _pick(jd, "id") or _pick(jd, "job_id") or ""
                        lifecycle_for_debug = _pick(jd, "lifecycle_state") or jd.get("lifecycleState") or ""
                        input_location = jd.get("input_location") or jd.get("inputLocation")
                        input_object_names = _extract_input_object_names(input_location)
                        if not input_object_names and job_id:
                            try:
                                full_job = get_transcription_job(job_id)
                                full_job_dict = _to_dict(full_job)
                                if isinstance(full_job_dict, dict):
                                    full_input = full_job_dict.get("input_location") or full_job_dict.get("inputLocation")
                                    input_object_names = _extract_input_object_names(full_input)
                            except Exception:
                                pass
                        if not any(_match_input_name(cand_name, n, default_prefix=default_prefix, allow_partial=True) for n in input_object_names):
                            continue
                        entry = {
                            "job_id": job_id,
                            "display_name": _pick(jd, "display_name") or jd.get("displayName"),
                            "lifecycle_state": lifecycle_for_debug,
                            "time_accepted": str(_pick(jd, "time_accepted") or jd.get("timeAccepted") or ""),
                            "time_finished": str(_pick(jd, "time_finished") or jd.get("timeFinished") or ""),
                            "input_object_name": cand_name,
                            "task_id": None,
                            "task_lifecycle_state": None,
                            "result_object_name": None,
                            "matched_via": "fuzzy_bucket_name",
                            "fuzzy_score": cand_score,
                            "fuzzy_query": object_name,
                        }
                        matches.append(entry)
                        break
            except Exception:
                pass

        matches.sort(key=lambda j: (j.get("time_accepted") or j.get("time_finished") or ""), reverse=True)
        best = matches[0] if matches else None
        logger.info(
            "tool=find_transcription_job_by_object success object=%s matches=%s best_job_id=%s",
            object_name,
            len(matches),
            best.get("job_id") if isinstance(best, dict) else None,
        )
        return json.dumps({
            "object_name": object_name,
            "object_name_candidates": object_candidates,
            "namespace": namespace or None,
            "bucket": bucket or None,
            "output_prefix": output_prefix,
            "lifecycle_filter": lifecycle_state,
            "lifecycle_filter_applied": lifecycle_for_api or None,
            "allow_partial_name_match": allow_partial_name_match,
            "enable_fuzzy_fallback": enable_fuzzy_fallback,
            "fuzzy_threshold": fuzzy_threshold,
            "max_job_scan": max_job_scan,
            "jobs_scanned": len(jobs),
            "jobs_bucket_matched": bucket_match_count,
            "count": len(matches),
            "best_match": best,
            "matches": matches,
            "fuzzy_candidates": fuzzy_candidates[:fuzzy_max_candidates] if fuzzy_candidates else [],
            "sample_scanned_jobs": scanned_job_inputs[:20],
            "debug": {
                "candidate_matched_any_scanned_input": any(c in seen_input_names for c in object_candidates),
                "sample_seen_input_object_names": sorted(seen_input_names)[:50],
                "sample_scanned_jobs": scanned_job_inputs[:20],
            } if include_debug else None,
        })
    except Exception as exc:
        logger.exception("tool=find_transcription_job_by_object failed object=%s error=%s", object_name, exc)
        return json.dumps({"error": str(exc), "object_name": object_name})
