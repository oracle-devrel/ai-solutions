import asyncio
import inspect
import json
import logging
import mimetypes
import os
import re
import time
import urllib.parse
from html import escape
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import gradio as gr
import oci
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware, wrap_tool_call
from langchain_community.chat_models.oci_generative_ai import ChatOCIGenAI
from langchain.messages import ToolMessage
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
try:
    from langchain_mcp_adapters.callbacks import Callbacks, CallbackContext
except Exception:  # pragma: no cover - backward compatibility with older adapters
    Callbacks = None  # type: ignore[assignment]
    CallbackContext = Any  # type: ignore[misc, assignment]

import agent_common as ac
from agent_common import payload_tools as pt
from auth.mcp_auth import build_mcp_server_config
from auth.oci_auth import load_runtime_oci_config_and_signer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("oracle_agent.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

load_dotenv()


def _new_intent_id() -> str:
    return f"intent-{int(time.time() * 1000)}"


def _extract_audio_filename_hint(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"([A-Za-z0-9._-]+\.(?:wav|mp3|m4a|flac|ogg|aac))", text, re.IGNORECASE)
    return str(match.group(1)).strip() if match else ""


def _extract_job_id(text: str) -> str:
    if not text:
        return ""
    match = ac.OCID_RE.search(text)
    if not match:
        return ""
    return match.group(0).strip().rstrip(".,;:)]}")

# ---------------------------------------------------------------------------
# Runtime memory hooks
# ---------------------------------------------------------------------------
def _save_persistent_memory(state: dict[str, Any]) -> None:
    # Runtime-only mode: no-op.
    return




async def tracing_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    def _runtime_snapshot(req: MCPToolCallRequest) -> dict[str, Any]:
        runtime = getattr(req, "runtime", None)
        if runtime is None:
            return {}
        snapshot: dict[str, Any] = {}
        context = getattr(runtime, "context", None)
        state = getattr(runtime, "state", None)
        store = getattr(runtime, "store", None)
        tool_call_id = getattr(runtime, "tool_call_id", None)
        if context is not None:
            snapshot["context"] = context if isinstance(context, dict) else str(context)
        if state is not None:
            if isinstance(state, dict):
                snapshot["state_keys"] = sorted(list(state.keys()))[:30]
            else:
                snapshot["state_type"] = str(type(state))
        snapshot["has_store"] = store is not None
        if tool_call_id:
            snapshot["tool_call_id"] = str(tool_call_id)
        return snapshot

    start = time.perf_counter()
    ts = ac.now_ts()
    intent_id = ac.CURRENT_INTENT_ID.get("")
    request_args = dict(request.args or {})
    safe_request_args = ac.redact_for_logging(request_args)
    runtime_snapshot = _runtime_snapshot(request)
    logger.info(
        "[MCP][REQUEST] ts=%s intent=%s tool=%s args=%s runtime=%s",
        ts,
        intent_id or "<none>",
        request.name,
        ac.json_preview(safe_request_args),
        ac.json_preview(runtime_snapshot, 800),
    )
    ac.add_activity_event(
        {
            "timestamp": ts,
            "intent_id": intent_id,
            "kind": "start",
            "text": f"{ac.human_tool_action(str(request.name))}...",
        }
    )
    try:
        result = await handler(request)
    except Exception as exc:
        logger.error(
            "[MCP][ERROR] ts=%s tool=%s err=%s",
            ts,
            request.name,
            str(exc),
        )
        ac.add_trace(
            {
                "timestamp": ts,
                "intent_id": intent_id,
                "tool_name": request.name,
                "args": safe_request_args,
                "runtime": runtime_snapshot,
                "result_summary": str(exc),
                "duration_ms": round((time.perf_counter() - start) * 1000),
                "status": "error",
            }
        )
        ac.add_activity_event(
            {
                "timestamp": ts,
                "intent_id": intent_id,
                "kind": "error",
                "text": f"{ac.human_tool_action(str(request.name))} failed",
            }
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000)
    texts = [getattr(block, "text", "") for block in (getattr(result, "content", []) or [])]
    if request.name == "upload_audio_to_bucket":
        for txt in texts:
            parsed = ac.parse_json(txt)
            if isinstance(parsed, dict):
                uploaded = parsed.get("uploaded_object")
                if uploaded:
                    ac.push_pending_uploaded_object(str(uploaded))
    logger.info(
        "[MCP][RESPONSE] ts=%s tool=%s duration_ms=%s text=%s",
        ts,
        request.name,
        duration_ms,
        ac.short_text("\\n".join(t for t in texts if t).strip(), 1600),
    )
    ac.add_trace(
        {
            "timestamp": ts,
            "intent_id": intent_id,
            "tool_name": request.name,
            "args": safe_request_args,
            "runtime": runtime_snapshot,
            "result_summary": "\n".join(t for t in texts if t).strip(),
            "duration_ms": duration_ms,
            "status": "success",
        }
    )
    ac.add_activity_event(
        {
            "timestamp": ts,
            "intent_id": intent_id,
            "kind": "done",
            "text": f"{ac.human_tool_action(str(request.name))} done",
        }
    )
    return result


async def payload_to_string_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    args = request.args or {}
    updated_args = dict(args)

    if request.name in pt.PAYLOAD_TOOL_ENRICHERS:
        updated_args = pt.normalize_payload_args(request.name, updated_args, logger=logger)
    elif request.name in pt.JOB_ID_TOOLS:
        updated_args = pt.normalize_job_id_args(updated_args)
    updated_args = pt.validate_tool_args(request.name, updated_args, logger=logger)

    if updated_args != args:
        request = request.override(args=updated_args)
    return await handler(request)


async def _mcp_progress_callback(progress: float, total: float | None, message: str | None, context: CallbackContext) -> None:
    tool_name = str(getattr(context, "tool_name", "") or "mcp_tool")
    ts = ac.now_ts()
    event = {
        "timestamp": ts,
        "tool_name": tool_name,
        "progress": progress,
        "total": total if total is not None else 100.0,
        "message": str(message or "").strip(),
    }
    ac.add_progress_event(event)
    intent_id = ac.CURRENT_INTENT_ID.get("")
    pct = 0
    if total not in (None, 0):
        try:
            pct = int((float(progress) / float(total)) * 100.0)
        except Exception:
            pct = 0
    marker = ac.should_emit_progress_marker(intent_id, tool_name, pct)
    if marker:
        ac.add_activity_event(
            {
                "timestamp": ts,
                "intent_id": intent_id,
                "kind": "progress",
                "text": f"{ac.human_tool_action(tool_name)} ({marker}%)",
            }
        )
    result_summary = f"{event['message']} progress={progress}/{event['total']}".strip()
    ac.add_trace(
        {
            "timestamp": ts,
            "intent_id": ac.CURRENT_INTENT_ID.get(""),
            "tool_name": f"{tool_name}:progress",
            "args": {},
            "runtime": {},
            "result_summary": result_summary,
            "duration_ms": 0,
            "status": "progress",
        }
    )
    logger.info("[MCP][PROGRESS] ts=%s tool=%s progress=%s total=%s message=%s", ts, tool_name, progress, total, message or "")


logger.info("Initializing OCI Generative AI model")
_genai_cfg, _genai_signer, _genai_auth_mode = load_runtime_oci_config_and_signer(
    logger=logger,
    connection_timeout=10.0,
    read_timeout=240.0,
)
logger.info(
    "GenAI auth mode=%s region=%s",
    _genai_auth_mode,
    _genai_cfg.get("region"),
)
_genai_client_kwargs: dict[str, Any] = {
    "config": _genai_cfg,
    "service_endpoint": os.getenv("SERVICE_ENDPOINT"),
    "retry_strategy": oci.retry.DEFAULT_RETRY_STRATEGY,
    "timeout": (10, 240),
}
if _genai_signer is not None:
    _genai_client_kwargs["signer"] = _genai_signer
_genai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(**_genai_client_kwargs)
llm = ChatOCIGenAI(
    client=_genai_client,
    model_id=os.getenv("MODEL_ID"),
    service_endpoint=os.getenv("SERVICE_ENDPOINT"),
    compartment_id=os.getenv("COMPARTMENT_ID"),
    model_kwargs={
        "temperature": float(os.getenv("MODEL_TEMPERATURE", "0.0")),
        "max_tokens": int(os.getenv("MODEL_MAX_TOKENS", "8192")),
    },
    provider=os.getenv("PROVIDER"),
)
logger.info("LLM initialized")

mcp_url = os.getenv("MCP_URL")
mcp_server_config = build_mcp_server_config(mcp_url=mcp_url, timeout=30.0, logger=logger)
logger.info(
    "MCP client config transport=%s url=%s headers=%s auth_enabled=%s compartment=%s namespace=%s bucket=%s environment=%s",
    mcp_server_config.get("transport"),
    mcp_server_config.get("url"),
    ac.json_preview(ac.redact_for_logging(mcp_server_config.get("headers", {})), 400),
    ac.env_bool("MCP_AUTH_ENABLED", False),
    ac.mask_ocid(os.getenv("COMPARTMENT_ID")),
    os.getenv("OCI_NAMESPACE") or "<unset>",
    os.getenv("SPEECH_BUCKET") or "<unset>",
    os.getenv("ENVIRONMENT") or "<unset>",
)
_client_kwargs: dict[str, Any] = {}
if Callbacks is not None:
    _client_kwargs["callbacks"] = Callbacks(on_progress=_mcp_progress_callback)
else:
    logger.warning("MCP progress callbacks unavailable: install/upgrade langchain-mcp-adapters with callback support")
client = MultiServerMCPClient(
    {"tools_server": mcp_server_config},
    tool_interceptors=[tracing_interceptor, payload_to_string_interceptor],
    **_client_kwargs,
)
logger.info("MCP client initialized -> %s", mcp_url)


async def _log_mcp_capabilities_once() -> None:
    try:
        tools = await client.get_tools()
        tool_names = [str(getattr(tool, "name", "") or "") for tool in tools]
        logger.info("MCP tool discovery success count=%s tools=%s", len(tool_names), tool_names)
    except Exception as exc:
        logger.exception("MCP tool discovery failed error=%s", exc)

    try:
        async with client.session("tools_server") as session:
            config_result = await session.read_resource("config://oci-defaults")
        config_text = ""
        for block in (getattr(config_result, "contents", []) or [config_result]):
            text = getattr(block, "text", None) or (str(block) if block else "")
            if text:
                config_text = text
                break
        logger.info("MCP config resource read success preview=%s", ac.json_preview(ac.parse_json(config_text) or config_text, 800))
    except Exception as exc:
        logger.exception("MCP config resource read failed error=%s", exc)


async def _log_mcp_capabilities_once() -> None:
    try:
        tools = await client.get_tools()
        tool_names = [str(getattr(tool, "name", "") or "") for tool in tools]
        logger.info("MCP tool discovery success count=%s tools=%s", len(tool_names), tool_names)
    except Exception as exc:
        logger.exception("MCP tool discovery failed error=%s", exc)

    try:
        async with client.session("tools_server") as session:
            config_result = await session.read_resource("config://oci-defaults")
        config_text = ""
        for block in (getattr(config_result, "contents", []) or [config_result]):
            text = getattr(block, "text", None) or (str(block) if block else "")
            if text:
                config_text = text
                break
        logger.info("MCP config resource read success preview=%s", ac.json_preview(ac.parse_json(config_text) or config_text, 800))
    except Exception as exc:
        logger.exception("MCP config resource read failed error=%s", exc)


# ---------------------------------------------------------------------------
# OCI Object Storage helpers + local tool
# ---------------------------------------------------------------------------

def _create_os_client() -> oci.object_storage.ObjectStorageClient:
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()

    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=120.0,
    )
    logger.info(
        "Object Storage client auth mode=%s region=%s",
        auth_mode,
        config.get("region"),
    )
    if signer is not None:
        return oci.object_storage.ObjectStorageClient(config=config, signer=signer)
    return oci.object_storage.ObjectStorageClient(config=config)


def _load_bucket_choices() -> tuple[list[str], str, str, str]:
    cfg = ac.build_speech_config()
    configured_namespace = str(cfg.get("namespace") or os.getenv("OCI_NAMESPACE") or "").strip()
    configured_bucket = str(cfg.get("bucket_name") or os.getenv("SPEECH_BUCKET") or "").strip()
    compartment_id = str(
        os.getenv("SPEECH_COMPARTMENT_OCID")
        or os.getenv("COMPARTMENT_ID")
        or ""
    ).strip()

    fallback_choices = [configured_bucket] if configured_bucket else []
    if not compartment_id:
        return fallback_choices, configured_bucket, configured_namespace, "Compartment not set; showing configured bucket only."

    try:
        os_client = _create_os_client()
        namespace = configured_namespace
        if not namespace:
            namespace_resp = os_client.get_namespace()
            namespace = str(getattr(namespace_resp, "data", namespace_resp) or "").strip()

        if not namespace:
            return fallback_choices, configured_bucket, configured_namespace, "Namespace not resolved; showing configured bucket only."

        names: list[str] = []
        response = os_client.list_buckets(
            namespace_name=namespace,
            compartment_id=compartment_id,
            limit=1000,
        )
        response_data = getattr(response, "data", None)
        bucket_items = getattr(response_data, "items", None) or response_data or []
        for item in bucket_items:
            name = str(getattr(item, "name", "") or "").strip()
            if name:
                names.append(name)
        choices = sorted(set(names), key=str.lower)
        if configured_bucket and configured_bucket not in choices:
            choices.insert(0, configured_bucket)
        selected = configured_bucket or (choices[0] if choices else "")
        if not choices and selected:
            choices = [selected]
        return choices, selected, namespace, ""
    except Exception as exc:
        logger.warning("Bucket discovery failed: %s", exc)
        return fallback_choices, configured_bucket, configured_namespace, f"Bucket discovery failed: {exc}"


def _runtime_bucket_text(namespace: str, bucket: str, note: str = "") -> str:
    ns = namespace or "<unset>"
    bk = bucket or "<unset>"
    base = f"`{ns}/{bk}`"
    if note:
        return f"{base}\n\n<span class='runtime-storage-note'>{escape(note)}</span>"
    return base


def _sync_runtime_storage_env(namespace: str, bucket: str, state: dict[str, Any]) -> None:
    ns = str(namespace or "").strip()
    bk = str(bucket or "").strip()
    if ns:
        os.environ["OCI_NAMESPACE"] = ns
        state["runtime_namespace"] = ns
    if bk:
        os.environ["SPEECH_BUCKET"] = bk
        state["runtime_bucket"] = bk


def _on_refresh_buckets(session_state: dict[str, Any]) -> tuple[dict[str, Any], Any, Any]:
    state = ac.ensure_state(session_state)
    choices, selected, namespace, note = _load_bucket_choices()
    _sync_runtime_storage_env(namespace, selected, state)
    dropdown_update = gr.update(choices=choices, value=selected)
    runtime_text_update = gr.update(value=_runtime_bucket_text(namespace, selected, note))
    return state, dropdown_update, runtime_text_update


def _on_bucket_selected(selected_bucket: str, session_state: dict[str, Any]) -> dict[str, Any]:
    state = ac.ensure_state(session_state)
    namespace = str(state.get("runtime_namespace") or os.getenv("OCI_NAMESPACE") or "").strip()
    bucket = str(selected_bucket or "").strip()
    _sync_runtime_storage_env(namespace, bucket, state)
    return state


def _upload_audio(audio_path: str) -> str:
    cfg = ac.build_speech_config()
    namespace, bucket = cfg["namespace"], cfg["bucket_name"]
    if not namespace or not bucket:
        raise ValueError("Missing OCI_NAMESPACE or SPEECH_BUCKET")

    source = Path(audio_path)
    if not source.exists():
        raise FileNotFoundError(f"File not found: {audio_path}")

    # Keep the uploaded object name identical to the local filename to avoid
    # mismatch when the agent/tool refers to the original name with spaces.
    object_name = source.name
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"

    os_client = _create_os_client()
    collision_index = 0
    candidate_name = object_name
    while True:
        try:
            os_client.head_object(
                namespace_name=namespace,
                bucket_name=bucket,
                object_name=candidate_name,
            )
            collision_index += 1
            stem = Path(object_name).stem
            suffix = Path(object_name).suffix
            candidate_name = f"{stem}_{collision_index}{suffix}"
        except Exception:
            object_name = candidate_name
            break

    with source.open("rb") as handle:
        os_client.put_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=object_name,
            put_object_body=handle,
            content_type=content_type,
        )

    logger.info(
        "upload_audio client file=%s object_name=%s namespace=%s bucket=%s content_type=%s size_bytes=%s",
        source.name,
        object_name,
        namespace,
        bucket,
        content_type,
        source.stat().st_size,
    )
    return object_name


@tool
def upload_audio_to_bucket(file_path: str) -> str:
    """Upload a local audio file to the configured OCI Object Storage bucket."""
    try:
        object_name = _upload_audio(file_path)
        cfg = ac.build_speech_config()
        return json.dumps(
            {
                "status": "uploaded",
                "file_path": file_path,
                "file_name": Path(file_path).name,
                "uploaded_object": object_name,
                "namespace": cfg.get("namespace"),
                "bucket": cfg.get("bucket_name"),
            }
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc), "file_path": file_path})


# ---------------------------------------------------------------------------
# MCP resource cache
# ---------------------------------------------------------------------------
_mcp_config: dict[str, Any] = {}
_mcp_docs: dict[str, str] = {}


async def _read_mcp_resources() -> None:
    global _mcp_config, _mcp_docs
    try:
        async with client.session("tools_server") as session:
            config_result = await session.read_resource("config://oci-defaults")
            docs_result = await session.read_resource("docs://oracle-speech")

        config_text = ""
        for block in (getattr(config_result, "contents", []) or [config_result]):
            text = getattr(block, "text", None) or (str(block) if block else "")
            if text:
                config_text = text
                break

        docs_text = ""
        for block in (getattr(docs_result, "contents", []) or [docs_result]):
            text = getattr(block, "text", None) or (str(block) if block else "")
            if text:
                docs_text = text
                break

        if config_text:
            _mcp_config.update(json.loads(config_text))
        if docs_text:
            _mcp_docs.update(json.loads(docs_text))

        logger.info("Loaded MCP resources config/docs")
    except Exception as exc:
        logger.warning("Could not read MCP resources: %s", exc)


# ---------------------------------------------------------------------------
# Agent graph + orchestration
# ---------------------------------------------------------------------------
_agent_graph = None
_agent_lock = asyncio.Lock()


def _build_agent_system_prompt() -> str:
    model = _mcp_config.get("default_model") or ac.build_speech_config().get("model_type")
    tool_signatures = (
        "Tool signatures (use exact args first, put optional fields in payload JSON):\n"
        "- sentiment_analysis(text)\n"
        "- upload_audio_to_bucket(file_path)\n"
        "- process_audio(object_name=None, payload=None)\n"
        "- create_speech_transcription_job(file_names=None, job_name=None, payload=None)\n"
        "- get_speech_transcription_job(job_id)\n"
        "- list_speech_transcription_jobs(compartment_id=None, payload=None)\n"
        "- cancel_speech_transcription_job(job_id)\n"
        "- get_speech_transcription_text(job_id)\n"
        "- read_transcription_result(job_id)\n"
        "- list_bucket_audio_files(namespace=None, bucket_name=None, prefix=None, payload=None)\n"
        "- find_transcription_job_by_object(object_name=None, payload=None)\n"
        "- find_transcription_job_by_filename(filename=None, payload=None)\n"
    )
    return (
        "You are Oracle Cloud Speech Copilot. "
        "Use tools to fetch real data; never fabricate tool outputs. "
        "Conversation is stateful: use prior tool outputs from history and latest references. "
        "CRITICAL: speech job tools require job_id OCID (ocid1.aispeechtranscriptionjob...). "
        "Never pass display names where job_id is required. "
        "Decide tool sequence autonomously based on the user objective and tool outputs. "
        "Chain multiple tools within the same turn when intermediate results are required to satisfy the objective. "
        "Only ask the user a follow-up question when you are truly blocked by missing external input after attempting relevant tools. "
        "Response formatting policy: prefer display name and source filename over raw OCID. "
        "When mentioning job IDs, use short references unless user explicitly asks for full OCID. "
        "Tool-execution policy: do not narrate planned future tool calls (for example, 'I will now analyze'). "
        "Execute required tool calls in the same turn and return final completed output only. "
        "If blocked, state the blocker and exact missing input. "
        "When multiple independent files/jobs must be processed, batch tool calls within the same turn where possible. "
        "Prefer parallelizable tool calls when there are no data dependencies between them. "
        + tool_signatures
    )


def _is_hallucinated_tool_error(exc: Exception) -> bool:
    text = str(exc or "")
    upper = text.upper()
    return ("HALLUCINATED_ALL_TOOL_CALLS" in upper) or ("ALL GENERATED TOOL CALLS WERE HALLUCINATED" in upper)


def _agent_recursion_limit() -> int:
    raw = str(os.getenv("AGENT_RECURSION_LIMIT", "40")).strip()
    try:
        value = int(raw)
    except ValueError:
        value = 40
    return max(10, min(value, 120))


def _agent_max_concurrency() -> int:
    raw = str(os.getenv("AGENT_MAX_CONCURRENCY", "8")).strip()
    try:
        value = int(raw)
    except ValueError:
        value = 8
    return max(1, min(value, 32))


def _agent_tool_run_limit() -> int:
    raw = str(os.getenv("AGENT_TOOL_RUN_LIMIT", "36")).strip()
    try:
        value = int(raw)
    except ValueError:
        value = 36
    return max(4, min(value, 100))


def _agent_model() -> Any:
    return ac.prepare_agent_model(llm, logger)


@wrap_tool_call
async def _tool_error_middleware(request: Any, handler: Callable[[Any], Any]) -> Any:
    try:
        maybe_result = handler(request)
        if inspect.isawaitable(maybe_result):
            return await maybe_result
        return maybe_result
    except Exception as exc:
        tool_call = getattr(request, "tool_call", {}) or {}
        tool_call_id = str(tool_call.get("id") or "")
        tool_name = str(tool_call.get("name") or "unknown_tool")
        logger.error("[AGENT][TOOL_ERROR] tool=%s err=%s", tool_name, exc)
        return ToolMessage(
            content=f"Tool `{tool_name}` failed: {exc}",
            tool_call_id=tool_call_id,
        )


async def _get_agent_graph():
    global _agent_graph
    if _agent_graph is not None:
        return _agent_graph

    async with _agent_lock:
        if _agent_graph is not None:
            return _agent_graph
        tools = await client.get_tools()
        all_tools = list(tools)
        system_prompt = _build_agent_system_prompt()
        logger.info("[AGENT][SYSTEM_PROMPT] %s", ac.short_text(system_prompt, 2400))
        tool_limit_middleware = ToolCallLimitMiddleware(
            run_limit=_agent_tool_run_limit(),
            exit_behavior="continue",
        )
        _agent_graph = create_agent(
            model=_agent_model(),
            tools=all_tools,
            system_prompt=system_prompt,
            middleware=[tool_limit_middleware, _tool_error_middleware],
            name="oracle_mcp_agent",
        )
        logger.info(
            "Agent runtime initialized: langchain.agents.create_agent (tools=%s, recursion_limit=%s, max_concurrency=%s, tool_run_limit=%s)",
            len(all_tools),
            _agent_recursion_limit(),
            _agent_max_concurrency(),
            _agent_tool_run_limit(),
        )
        return _agent_graph


def _job_action_keywords(text: str) -> bool:
    lowered = text.lower()
    keywords = ["status", "job", "transcript", "summar", "sentiment", "cancel", "analy", "show"]
    return any(keyword in lowered for keyword in keywords)


def _short_job_id(job_id: str) -> str:
    value = str(job_id or "").strip()
    if len(value) <= 30:
        return value
    return f"{value[:18]}...{value[-8:]}"


def _style_job_ids_for_display(text: str) -> str:
    if not text:
        return text
    return ac.OCID_RE.sub(lambda m: f"<abbr title=\"{m.group(0)}\">{_short_job_id(m.group(0))}</abbr>", text)


def _job_summary_table_for_response(state: dict[str, Any], job_ids: list[str]) -> str:
    rows: list[str] = []
    jobs_by_id = state.get("jobs_by_id", {}) or {}
    for job_id in ac.merge_unique_str_list(job_ids)[:10]:
        meta = jobs_by_id.get(job_id, {}) if isinstance(jobs_by_id, dict) else {}
        source_files = meta.get("source_files") if isinstance(meta.get("source_files"), list) else []
        file_name = Path(str(source_files[0])).name if source_files else "-"
        display_name = str(meta.get("display_name") or "-")
        status = str(meta.get("status") or "-")
        rows.append(f"| {file_name} | {display_name} | {status} | <abbr title=\"{job_id}\">{_short_job_id(job_id)}</abbr> |")
    if not rows:
        return ""
    return rows


def _postprocess_assistant_response(user_text: str, assistant_text: str, state: dict[str, Any]) -> str:
    if not assistant_text:
        return assistant_text
    ids = [m.group(0) for m in ac.OCID_RE.finditer(assistant_text)]
    styled = _style_job_ids_for_display(assistant_text)
    lowered = (user_text or "").lower()
    asked_for_job_list = ("list" in lowered and "job" in lowered) or ("jobs" in lowered and "transcription" in lowered)
    if asked_for_job_list and len(ids) >= 2:
        table = _job_summary_table_for_response(state, ids)
        if table:
            styled = f"{styled}\n{table}"
    return styled


def _resolve_job_for_request(text: str, state: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    explicit = _extract_job_id(text)
    if ac.valid_job_id(explicit):
        return explicit, None

    return "", None


def _extract_agent_text(result: Any) -> str:
    messages = (result or {}).get("messages", []) if isinstance(result, dict) else []
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = "\n".join(str(chunk) for chunk in content)
            text = str(content or "").strip()
            if text:
                return text
    return ""


def _extract_agent_tool_calls(result: Any) -> list[str]:
    calls: list[str] = []
    messages = (result or {}).get("messages", []) if isinstance(result, dict) else []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if isinstance(call, dict):
                    name = str(call.get("name") or "").strip()
                    if name:
                        calls.append(name)
        addl = getattr(message, "additional_kwargs", {}) or {}
        alt_calls = addl.get("tool_calls") if isinstance(addl, dict) else None
        if isinstance(alt_calls, list):
            for call in alt_calls:
                if isinstance(call, dict):
                    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                    name = str(fn.get("name") or call.get("name") or "").strip()
                    if name:
                        calls.append(name)
    deduped: list[str] = []
    for name in calls:
        if name not in deduped:
            deduped.append(name)
    return deduped


def _public_message_for_tool_failures(traces: list[dict[str, Any]]) -> str:
    for trace in reversed(traces):
        tool_name = str(trace.get("tool_name", "") or "")
        status = str(trace.get("status", "") or "")
        parsed = ac.parse_json(trace.get("result_summary"))
        has_error_payload = isinstance(parsed, dict) and bool(parsed.get("error"))
        if status == "error" or has_error_payload:
            if tool_name == "sentiment_analysis":
                return "I couldn’t complete sentiment analysis right now. Please try again."
            if tool_name == "process_audio":
                return "I couldn’t complete audio processing right now. Please try again."
            return "I couldn’t complete that tool-backed request right now. Please try again."
    return ""


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if "text" in content:
            return _content_to_text(content.get("text"))
        if "content" in content:
            return _content_to_text(content.get("content"))
        return ac.short_text(json.dumps(content, ensure_ascii=False, default=str), 2400)
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = _content_to_text(item)
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()
    return str(content).strip()


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in history or []:
        role = str((item or {}).get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = _content_to_text((item or {}).get("content"))
        if text:
            normalized.append({"role": role, "content": text})
    return normalized


def _conversation_preview(messages: list[Any], limit: int = 6) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for msg in messages[-limit:]:
        role = "assistant" if isinstance(msg, AIMessage) else "user"
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = "\n".join(str(chunk) for chunk in content)
        preview.append({"role": role, "content": ac.short_text(str(content or "").replace("\n", " "), 220)})
    return preview


def _extract_upload_file_path(args: dict[str, Any]) -> str:
    raw_path = str((args or {}).get("file_path") or "")
    if not raw_path:
        return ""
    return Path(raw_path).name


def _extract_create_payload(args: dict[str, Any]) -> dict[str, Any]:
    payload = (args or {}).get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        loaded = ac.parse_json(payload)
        if isinstance(loaded, dict):
            return dict(loaded)
    return {}


def _download_result_object(namespace: str, bucket: str, object_name: str, job_id: str) -> str:
    if not namespace or not bucket or not object_name or not ac.valid_job_id(job_id):
        return ""
    ac.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_job = re.sub(r"[^A-Za-z0-9._-]", "_", job_id.split(".")[-1])[:80]
    local_path = ac.DOWNLOADS_DIR / f"transcript_{safe_job}_{Path(object_name).name}"
    if local_path.exists():
        return str(local_path)

    os_client = _create_os_client()
    resp = os_client.get_object(namespace_name=namespace, bucket_name=bucket, object_name=object_name)
    payload = resp.data.content if hasattr(resp.data, "content") else resp.data.read()
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    local_path.write_bytes(payload)
    return str(local_path)


def _download_link_markdown(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    href = f"/gradio_api/file={urllib.parse.quote(str(p))}"
    return f"[Download transcription JSON]({href})"


def _sync_state_from_traces(state: dict[str, Any], start_index: int, intent_id: str) -> None:
    traces = ac.get_traces_for_intent(intent_id, start_index=start_index)
    for trace in traces:
        if trace.get("status") != "success":
            continue

        tool_name = str(trace.get("tool_name", ""))
        args = trace.get("args") if isinstance(trace.get("args"), dict) else {}
        result_summary = str(trace.get("result_summary", ""))
        parsed = ac.parse_json(result_summary) or {}

        if tool_name == "upload_audio_to_bucket":
            file_name = _extract_upload_file_path(args)
            uploaded_object = str(parsed.get("uploaded_object") or "")
            if file_name and uploaded_object:
                state["uploaded_objects_by_file"].setdefault(file_name, [])
                if uploaded_object not in state["uploaded_objects_by_file"][file_name]:
                    state["uploaded_objects_by_file"][file_name].append(uploaded_object)
                state["file_by_uploaded_object"][uploaded_object] = file_name

        elif tool_name == "process_audio":
            job_id = str(parsed.get("job_id") or "")
            object_name = str(parsed.get("input_object_name") or "")
            lifecycle_state = str(parsed.get("lifecycle_state") or parsed.get("status") or "SUCCEEDED")
            text = str(parsed.get("transcription_text") or "")
            if ac.valid_job_id(job_id):
                source_name = state.get("file_by_uploaded_object", {}).get(object_name, object_name)
                ac.save_job(
                    state,
                    job_id,
                    display_name=str(parsed.get("display_name") or ""),
                    status=lifecycle_state,
                    source_file=source_name,
                    uploaded_object=object_name,
                )
                if object_name:
                    state["job_id_by_uploaded_object"][object_name] = job_id
                if text:
                    state["transcript_cache_by_job_id"][job_id] = text

        elif tool_name == "create_speech_transcription_job":
            job = parsed.get("job") if isinstance(parsed.get("job"), dict) else {}
            params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
            job_id = str(job.get("job_id") or "")
            display_name = str(params.get("job_name") or "")
            status = str(parsed.get("status") or "submitted")
            file_names = params.get("file_names") if isinstance(params.get("file_names"), list) else []
            if ac.valid_job_id(job_id):
                if file_names:
                    for item in file_names:
                        obj = str(item or "")
                        source_name = state.get("file_by_uploaded_object", {}).get(obj, obj)
                        if obj and ac.valid_job_id(job_id):
                            state["job_id_by_uploaded_object"][obj] = job_id
                        ac.save_job(
                            state,
                            job_id,
                            display_name=display_name,
                            status=status,
                            source_file=source_name,
                            uploaded_object=obj,
                        )
                else:
                    ac.save_job(state, job_id, display_name=display_name, status=status)

        elif tool_name in {"get_speech_transcription_job", "cancel_speech_transcription_job"}:
            job_id = str(parsed.get("job_id") or args.get("job_id") or "")
            status = str(parsed.get("lifecycle_state") or parsed.get("status") or "")
            if ac.valid_job_id(job_id):
                ac.save_job(state, job_id, status=status)

        elif tool_name == "list_speech_transcription_jobs":
            jobs = parsed.get("jobs") if isinstance(parsed.get("jobs"), list) else []
            for item in reversed(jobs):
                if not isinstance(item, dict):
                    continue
                job_id = str(item.get("job_id") or item.get("id") or "")
                status = str(item.get("status") or item.get("lifecycle_state") or "")
                display_name = str(item.get("display_name") or "")
                if ac.valid_job_id(job_id):
                    ac.save_job(state, job_id, display_name=display_name, status=status)

        elif tool_name in {"get_speech_transcription_text", "read_transcription_result"}:
            job_id = str(parsed.get("job_id") or args.get("job_id") or "")
            text = str(parsed.get("transcription_text") or "")
            if ac.valid_job_id(job_id):
                ac.save_job(state, job_id, status=str(parsed.get("lifecycle_state") or "SUCCEEDED"))
                if text:
                    state["transcript_cache_by_job_id"][job_id] = text
                if tool_name == "read_transcription_result":
                    namespace = str(parsed.get("namespace_name") or "")
                    bucket = str(parsed.get("bucket_name") or "")
                    object_name = str(parsed.get("result_object_name") or "")
                    try:
                        local_path = _download_result_object(namespace, bucket, object_name, job_id)
                    except Exception as exc:
                        local_path = ""
                    if local_path:
                        state["downloaded_result_by_job_id"][job_id] = local_path

        elif tool_name in {"find_transcription_job_by_filename", "find_transcription_job_by_object"}:
            matches = parsed.get("matches") if isinstance(parsed.get("matches"), list) else []
            for match in matches:
                if not isinstance(match, dict):
                    continue
                job_id = str(match.get("job_id") or "").strip()
                text = str(match.get("transcription_text") or "").strip()
                lifecycle_state = str(match.get("lifecycle_state") or "").strip()
                object_name = str(match.get("input_object_name") or "").strip()
                if ac.valid_job_id(job_id):
                    ac.save_job(state, job_id, status=lifecycle_state or "SUCCEEDED", source_file=object_name)
                    if text:
                        state["transcript_cache_by_job_id"][job_id] = text

        elif tool_name == "sentiment_analysis":
            state["last_sentiment_result"] = parsed if isinstance(parsed, dict) and parsed else result_summary

    _save_persistent_memory(state)


async def _invoke_agent(text: str, audio_files: list[str], history: list[dict[str, str]], state: dict[str, Any]) -> str:
    state = ac.ensure_state(state)
    intent_id = _new_intent_id()
    state["active_intent_id"] = intent_id
    user_text = (text or "").strip()
    if user_text.lower() == "help":
        return (
            "Available tools:\n"
            "- process_audio\n"
            "- sentiment_analysis"
        )
    logger.info("[AGENT][USER] intent=%s text=%s audio_files=%s", intent_id, user_text, len(audio_files))

    resolved_job_id, pending = _resolve_job_for_request(user_text, state)
    if pending:
        state["pending_choice"] = pending
        return pending.get("prompt", "Please select the target to continue.")

    file_hint = _extract_audio_filename_hint(user_text)

    attachment_hint = ""
    if audio_files:
        for path in audio_files:
            try:
                object_name = _upload_audio(path)
                ac.push_pending_uploaded_object(object_name)
                logger.info("agent attachment queued local_path=%s uploaded_object=%s", path, object_name)
            except Exception as exc:
                logger.warning("Auto-upload failed for attachment=%s error=%s", path, exc)
        file_names = [Path(path).name for path in audio_files]
        lines = [
            "Attached local audio files:",
            *[f"- {name}" for name in file_names],
            "These files are already uploaded in this UI turn; do not ask user to upload again.",
            "Call process_audio for each file using uploaded object_name.",
        ]
        attachment_hint = "\n" + "\n".join(lines)

    memory_hint_lines: list[str] = []
    if resolved_job_id and ac.valid_job_id(resolved_job_id):
        memory_hint_lines.append(f"Resolved target job_id for this request: {resolved_job_id}")
    latest_known = str(state.get("latest_job_id") or "")
    if ac.valid_job_id(latest_known):
        memory_hint_lines.append(f"Latest known job_id: {latest_known}")
    active_job_id = resolved_job_id if ac.valid_job_id(resolved_job_id) else latest_known
    if ac.valid_job_id(active_job_id):
        active_job = (state.get("jobs_by_id") or {}).get(active_job_id, {})
        active_status = str((active_job or {}).get("status") or "UNKNOWN")
        transcript = str((state.get("transcript_cache_by_job_id") or {}).get(active_job_id) or "")
        memory_hint_lines.append(f"Active job status: {active_status}")
        memory_hint_lines.append(f"Cached transcript available: {'yes' if transcript else 'no'}")
    if file_hint and not resolved_job_id:
        memory_hint_lines.append(
            "User referenced filename that is not yet mapped in runtime memory. "
            "Resolve autonomously using transcription tools (find/list/get) and continue without asking for explicit job_id unless truly ambiguous."
        )

    prompt = user_text
    if attachment_hint:
        prompt += attachment_hint

    graph = await _get_agent_graph()
    conv_messages: list[Any] = []
    if memory_hint_lines:
        conv_messages.append(SystemMessage(content="Runtime context:\n" + "\n".join(memory_hint_lines)))
    normalized_history = _normalize_history(history)
    for item in normalized_history[-10:]:
        role = str((item or {}).get("role", "")).strip().lower()
        content = str((item or {}).get("content", "")).strip()
        if not content:
            continue
        conv_messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))
    conv_messages.append(HumanMessage(content=prompt))
    logger.info(
        "[AGENT][INPUT] intent=%s resolved_job_id=%s history_msgs=%s prompt=%s conv_preview=%s speech_cfg=%s",
        intent_id,
        resolved_job_id or "<none>",
        len(conv_messages),
        ac.short_text(prompt.replace("\n", " "), 360),
        ac.json_preview(_conversation_preview(conv_messages), 1600),
        ac.json_preview(ac.build_speech_config(), 800),
    )


    trace_start = len(ac.get_traces())
    token = ac.CURRENT_INTENT_ID.set(intent_id)
    invoke_config = {
        "recursion_limit": _agent_recursion_limit(),
        "max_concurrency": _agent_max_concurrency(),
        "configurable": {
            "resolved_job_id": resolved_job_id or "",
            "latest_known_job_id": str(state.get("latest_job_id") or ""),
            "has_audio_attachments": bool(audio_files),
            "audio_file_count": len(audio_files),
        },
        "tags": ["oracle-mcp-agent", "speech-copilot"],
        "metadata": {
            "audio_file_count": len(audio_files),
        },
    }
    retry_hint = SystemMessage(
        content=(
            "Tool-call retry mode: Use only declared tool names and exact argument keys from schema. "
            "Do not invent argument names. Prefer optional fields under payload JSON."
        )
    )
    invoke_messages = list(conv_messages)
    result: Any
    try:
        for attempt in range(2):
            try:
                result = await graph.ainvoke({"messages": invoke_messages}, config=invoke_config)
                break
            except Exception as exc:
                logger.error("[AGENT][INVOKE_ERROR] intent=%s attempt=%s err=%s", intent_id, attempt, exc)  

                if attempt == 0:
                    if _is_hallucinated_tool_error(exc):
                        logger.warning(
                            "[AGENT][RETRY] intent=%s reason=hallucinated_tool_calls retrying_with_strict_hint",
                            intent_id,
                        )
                        invoke_messages = [retry_hint, *conv_messages]
                    else:
                        logger.warning(
                            "[AGENT][RETRY] intent=%s reason=invoke_error retrying_once err=%s",
                            intent_id,
                            str(exc),
                        )
                    continue
                return f"Autonomous agent failed: {exc}"
        else:
            return "Autonomous agent failed: model tool-calling retry exhausted."
    finally:
        ac.CURRENT_INTENT_ID.reset(token)

    assistant_text = _extract_agent_text(result)
    planned_calls = _extract_agent_tool_calls(result)
    logger.info("[AGENT][TOOL_DECISION] intent=%s planned_tool_calls=%s", intent_id, planned_calls)
    if not assistant_text:
        assistant_text = "Completed autonomous run, but no assistant response text was returned."

    _sync_state_from_traces(state, trace_start, intent_id)

    found_job_id = _extract_job_id(assistant_text)
    assistant_text = _postprocess_assistant_response(user_text, assistant_text, state)
    new_traces = ac.get_traces_for_intent(intent_id, start_index=trace_start)
    if ac.valid_job_id(found_job_id):
        ac.save_job(state, found_job_id)
    tool_names = [str(trace.get("tool_name", "")) for trace in new_traces]
    logger.info(
        "[AGENT][OUTPUT] intent=%s tool_calls=%s tools=%s assistant=%s",
        intent_id,
        len(new_traces),
        tool_names,
        ac.short_text(assistant_text.replace("\n", " "), 360),
    )

    _save_persistent_memory(state)
    return assistant_text


# NOTE: Bypassed _run_agent_first wrapper and calling _invoke_agent directly.


# ---------------------------------------------------------------------------
# Selection + action helpers
# ---------------------------------------------------------------------------

def _autonomous_actions(state: dict[str, Any]) -> list[str]:
    return [
        "List bucket audio files",
        "List transcription jobs",
        "Show transcript of my latest job",
        "Analyze sentiment of latest transcript",
        "Check status of my latest job",
        "Find job by filename",
    ]


def _action_updates(state: dict[str, Any]) -> list[gr.Button]:
    labels = _autonomous_actions(state)
    updates: list[gr.Button] = []
    for index in range(6):
        if index < len(labels):
            updates.append(gr.Button(value=labels[index], visible=True, variant="secondary", size="sm"))
        else:
            updates.append(gr.Button(visible=False))
    return updates


async def _execute_pending_choice(choice_label: str, state: dict[str, Any]) -> str:
    pending = state.get("pending_choice")
    if not pending:
        return "No pending selection."

    selected = next((item for item in pending.get("options", []) if item.get("label") == choice_label), None)
    state["pending_choice"] = None
    if not selected:
        return "Selection is no longer valid. Please retry."

    if pending.get("kind") == "job":
        selected_job = str(selected.get("job_id") or "")
        action_text = str(pending.get("action") or "Continue with original request")
        if ac.valid_job_id(selected_job):
            ac.save_job(state, selected_job)
            prompt = f"Use this exact job_id: {selected_job}. Continue this request: {action_text}"
            return await _invoke_agent(prompt, [], [], state)

    return "Unable to continue with selected option."


# ---------------------------------------------------------------------------
# UI handlers
# ---------------------------------------------------------------------------


def _compose_updates(
    state: dict[str, Any],
    run_status_text: str = "Ask a question to begin.",
    run_status_mode: str = "ready",
) -> tuple[Any, ...]:
    choice_notice, choice_detail, choice_buttons, choice_selector, choice_apply = ac.choice_updates(state)
    return (
        ac.context_markdown(state, ac.short_text),
        gr.Markdown(value="", visible=False),
        ac.activity_markdown(state),
        choice_notice,
        choice_detail,
        *choice_buttons,
        choice_selector,
        choice_apply,
    )


def _reset_composer():
    return gr.update(value={"text": "", "files": []})


async def _chat_turn(user_input: dict, history: list, session_state: dict):
    state = ac.ensure_state(session_state)
    text = str((user_input or {}).get("text", "")).strip()
    files = ac.extract_file_paths((user_input or {}).get("files", []))
    audio_files = [path for path in files if ac.is_audio_file(path)]

    if not text and not audio_files:
        yield history, state, *_compose_updates(state)
        return

    display = text
    if audio_files:
        uploaded_names = ", ".join(Path(path).name for path in audio_files)
        display = (f"{text}\n\n" if text else "") + f"Uploaded: **{uploaded_names}**"

    pending_history = history + [{"role": "user", "content": display}]
    working_history = pending_history + [{"role": "assistant", "content": ac.working_message("In progress: working on your request, gathering results")}]
    ac.clear_progress_events()
    ac.clear_activity_events()
    yield working_history, state, *_compose_updates(state, "In progress: working on your request", "running")

    task = asyncio.create_task(_invoke_agent(text, audio_files, pending_history[:-1], state))
    last_progress_text = ""
    last_activity_signature = ""
    while not task.done():
        progress_text = ac.latest_progress_text()
        activity_rows = ac.get_recent_activity(str(state.get("active_intent_id") or ""), limit=1)
        activity_signature = ""
        activity_text = ""
        if activity_rows:
            latest = activity_rows[-1]
            activity_signature = f"{latest.get('timestamp', '')}::{latest.get('text', '')}"
            activity_text = str(latest.get("text") or "").strip()
        if (progress_text and progress_text != last_progress_text) or (activity_signature and activity_signature != last_activity_signature):
            last_progress_text = progress_text or last_progress_text
            last_activity_signature = activity_signature or last_activity_signature
            live_text = progress_text or activity_text or "gathering results"
            live_history = pending_history + [{"role": "assistant", "content": ac.working_message(f"In progress: {live_text}")}]
            yield live_history, state, *_compose_updates(state, f"In progress: {live_text}", "running")
        await asyncio.sleep(0.5)

    reply = await task
    final_history = pending_history + [{"role": "assistant", "content": reply}]
    yield final_history, state, *_compose_updates(state, "Done", "done")


async def _choice_click(choice_label: str, history: list, session_state: dict):
    state = ac.ensure_state(session_state)
    if not choice_label:
        return history, state, *_compose_updates(state)

    history = history + [{"role": "user", "content": f"Selected: {choice_label}"}]
    reply = await _execute_pending_choice(choice_label, state)
    history = history + [{"role": "assistant", "content": reply}]
    return history, state, *_compose_updates(state)


async def _choice_apply(selected_label: str, history: list, session_state: dict):
    return await _choice_click(selected_label, history, session_state)


async def _action_click(action_label: str, history: list, session_state: dict):
    async for update in _chat_turn({"text": action_label, "files": []}, history, session_state):
        yield update


# ---------------------------------------------------------------------------
# Inspector helpers
# ---------------------------------------------------------------------------

def _on_launch_inspector(server_url: str, client_port: str, server_port: str):
    cp = int(client_port) if client_port.strip().isdigit() else 6274
    sp = int(server_port) if server_port.strip().isdigit() else 6277
    launch_msg = ac.launch_inspector(client_port=cp, server_port=sp)
    target = str(server_url or "").strip()
    if target:
        launch_msg = f"{launch_msg}\n\nTarget MCP URL: `{target}`"
    return launch_msg, ac.inspector_status()


def _on_stop_inspector():
    return ac.stop_inspector(), ac.inspector_status()


def _on_refresh_status():
    return ac.inspector_status()


# ---------------------------------------------------------------------------
# Visual design
# ---------------------------------------------------------------------------
_theme = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#fff6f4",
        c100="#ffe8e2",
        c200="#ffd0c5",
        c300="#ffae9b",
        c400="#f17f67",
        c500=ac.ORACLE_RED,
        c600="#a73729",
        c700="#84291f",
        c800="#652018",
        c900="#481611",
        c950="#2d0d0a",
    ),
    neutral_hue="stone",
)

# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Starting Oracle Cloud AI Agent UI")
    try:
        asyncio.run(_log_mcp_capabilities_once())
    except Exception:
        logger.exception("Initial MCP capability probe failed")
    try:
        asyncio.run(_read_mcp_resources())
    except Exception:
        logger.exception("MCP resource prefetch failed")

    cfg = ac.build_speech_config()
    bucket_choices, selected_bucket, selected_namespace, _ = _load_bucket_choices()
    # Keep runtime env aligned with initial UI selection.
    _sync_runtime_storage_env(selected_namespace, selected_bucket, {})
    model = _mcp_config.get("default_model") or cfg.get("model_type")
    public_mcp_url = ac.resolve_public_mcp_url(mcp_url)

    with gr.Blocks(title="Oracle Cloud Speech Copilot", fill_height=True) as app:
        with gr.Group(elem_classes=["top-masthead"]):
            with gr.Row(elem_classes=["masthead-row"]):
                gr.HTML(
                    "<div class='brand-block'>"
                    f"  <img src='{ac.logo_src_for_html()}' alt='Oracle'/>"
                    "  <div>"
                    "    <h2 class='brand-title'>OCI Speech Copilot</h2>"
                    "    <p class='brand-subtitle'>Ask anything, use tools as needed, and get OCI Speech results in one place.</p>"
                    "  </div>"
                    "</div>"
                )
                with gr.Row(elem_classes=["chip-row", "masthead-chip-controls"]):
                    gr.HTML(f"<span class='info-chip'><strong>MCP URL</strong> {public_mcp_url or '<unset>'}</span>")
                    with gr.Row(elem_classes=["bucket-chip-wrap"]):
                        gr.HTML("<span class='bucket-chip-label'>Audio Bucket</span>")
                        bucket_selector = gr.Dropdown(
                            choices=bucket_choices,
                            value=selected_bucket or (bucket_choices[0] if bucket_choices else None),
                            interactive=True,
                            allow_custom_value=False,
                            container=False,
                            show_label=False,
                            elem_classes=["bucket-chip-dropdown"],
                            min_width=140,
                        )
                    gr.HTML(f"<span class='info-chip'><strong>Model</strong> {model or '<unset>'}</span>")
        session_state = gr.State(ac.default_session_state())

        with gr.Column(elem_classes=["frame-wrap"]):
            with gr.Column(scale=12, min_width=520, elem_classes=["chat-workspace"]):
                with gr.Group(elem_classes=["chat-surface"]):
                    context_md = gr.Markdown("_No context yet._", visible=False)
                    run_status_md = gr.Markdown(value="", visible=False)
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=560,
                        avatar_images=(None, ac.logo_src_for_avatar()),
                        buttons=["copy"],
                    )
                    activity_md = gr.Markdown(value="", visible=False)
                    choice_notice = gr.Markdown(value="", visible=False)
                    choice_detail = gr.Markdown(value="", visible=False, elem_classes=["choice-detail"])
                    with gr.Row(elem_classes=["choice-row"]):
                        choice_btn_1 = gr.Button(visible=False)
                        choice_btn_2 = gr.Button(visible=False)
                        choice_btn_3 = gr.Button(visible=False)
                        choice_btn_4 = gr.Button(visible=False)
                        choice_btn_5 = gr.Button(visible=False)
                    with gr.Row():
                        choice_selector = gr.Dropdown(choices=[], label="Select Target", visible=False, interactive=True, scale=4)
                        choice_apply_btn = gr.Button("Apply Selection", visible=False, variant="primary", scale=1)
                prompt_seed = gr.Textbox(visible=False)
                with gr.Group(elem_classes=["quick-prompts-panel"]):
                    with gr.Row(elem_classes=["quick-prompts-row"]):
                        quick_prompt_1 = gr.Button("Process uploaded audio", elem_classes=["quick-prompt-chip"], size="sm")
                        quick_prompt_2 = gr.Button("Analyze sentiment", elem_classes=["quick-prompt-chip"], size="sm")
                        quick_prompt_3 = gr.Button("help", elem_classes=["quick-prompt-chip"], size="sm")
                with gr.Group(elem_classes=["composer-dock"]):
                    composer = gr.MultimodalTextbox(
                        placeholder="Type your request or attach audio (.wav/.mp3/.m4a/.flac/.ogg/.aac)",
                        show_label=False,
                        file_types=list(ac.AUDIO_EXTENSIONS),
                    )
                with gr.Accordion("Inspector", open=False, elem_classes=["inspector-panel"]):
                    with gr.Row():
                        insp_url = gr.Textbox(label="MCP Server URL", value=public_mcp_url or "", scale=3)
                    with gr.Row():
                        insp_cp = gr.Textbox(label="Inspector UI port", value="6274")
                        insp_sp = gr.Textbox(label="Proxy port", value="6277")
                    with gr.Row():
                        launch_btn = gr.Button("Launch", variant="primary")
                        stop_btn = gr.Button("Stop", variant="stop")
                        status_btn = gr.Button("Refresh", variant="secondary")
                    insp_output = gr.Markdown(label="Inspector output")
                    insp_status = gr.Markdown(value=ac.inspector_status())

        chat_outputs = [
            chatbot,
            session_state,
            context_md,
            run_status_md,
            activity_md,
            choice_notice,
            choice_detail,
            choice_btn_1,
            choice_btn_2,
            choice_btn_3,
            choice_btn_4,
            choice_btn_5,
            choice_selector,
            choice_apply_btn,
        ]

        prompt_seed.change(
            fn=lambda text: {"text": text or "", "files": []},
            inputs=[prompt_seed],
            outputs=[composer],
            show_progress="hidden",
        )

        for quick_button in [quick_prompt_1, quick_prompt_2, quick_prompt_3]:
            quick_button.click(fn=lambda text: text, inputs=[quick_button], outputs=[prompt_seed], show_progress="hidden")

        composer.submit(
            fn=_chat_turn,
            inputs=[composer, chatbot, session_state],
            outputs=chat_outputs,
        ).then(fn=_reset_composer, outputs=[composer])

        for button in [choice_btn_1, choice_btn_2, choice_btn_3, choice_btn_4, choice_btn_5]:
            button.click(fn=_choice_click, inputs=[button, chatbot, session_state], outputs=chat_outputs)
        choice_apply_btn.click(fn=_choice_apply, inputs=[choice_selector, chatbot, session_state], outputs=chat_outputs)
        bucket_selector.change(
            fn=_on_bucket_selected,
            inputs=[bucket_selector, session_state],
            outputs=[session_state],
            show_progress="minimal",
        )

        launch_btn.click(
            fn=_on_launch_inspector,
            inputs=[insp_url, insp_cp, insp_sp],
            outputs=[insp_output, insp_status],
            show_progress="minimal",
        )
        stop_btn.click(fn=_on_stop_inspector, outputs=[insp_output, insp_status], show_progress="minimal")
        status_btn.click(fn=_on_refresh_status, outputs=[insp_status], show_progress="minimal")

        gr.Markdown("<div class='footer'>OCI MCP conversational demo | UI redesigned, backend agentic flow preserved</div>")

    ac.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.launch(
        theme=_theme,
        css=ac.CUSTOM_CSS,
        allowed_paths=[str(ac.ORACLE_LOGO_PRIMARY_PATH.parent), str(ac.DOWNLOADS_DIR)],
    )


if __name__ == "__main__":
    main()
