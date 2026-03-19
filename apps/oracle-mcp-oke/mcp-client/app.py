# agent_client.py
import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
import oci
from dotenv import load_dotenv
from langchain_community.chat_models.oci_generative_ai import ChatOCIGenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from langgraph.prebuilt import create_react_agent
from auth.mcp_auth import build_mcp_server_config
from oci_auth import load_runtime_oci_config_and_signer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# MCP Tool Call Trace Store
# ---------------------------------------------------------------------------
_tool_call_traces: list[dict[str, Any]] = []
_trace_lock = threading.Lock()
_MAX_TRACES = 200


def _add_trace(entry: dict[str, Any]) -> None:
    with _trace_lock:
        _tool_call_traces.append(entry)
        if len(_tool_call_traces) > _MAX_TRACES:
            del _tool_call_traces[: len(_tool_call_traces) - _MAX_TRACES]


def _get_traces() -> list[dict[str, Any]]:
    with _trace_lock:
        return list(_tool_call_traces)


def _clear_traces() -> None:
    with _trace_lock:
        _tool_call_traces.clear()


# ---------------------------------------------------------------------------
# MCP Inspector subprocess management
# ---------------------------------------------------------------------------
_inspector_process: subprocess.Popen | None = None
_inspector_lock = threading.Lock()


def _launch_inspector(client_port: int = 6274, server_port: int = 6277) -> str:
    """Launch the MCP Inspector via npx as a background subprocess."""
    global _inspector_process

    npx_cmd = shutil.which("npx")
    if not npx_cmd:
        return "**Error:** `npx` not found on PATH. Install Node.js >= 22 to use the MCP Inspector."

    with _inspector_lock:
        if _inspector_process is not None and _inspector_process.poll() is None:
            _inspector_process.terminate()
            try:
                _inspector_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _inspector_process.kill()

        env = {**os.environ, "CLIENT_PORT": str(client_port), "SERVER_PORT": str(server_port)}
        try:
            _inspector_process = subprocess.Popen(
                [npx_cmd, "@modelcontextprotocol/inspector"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            return f"**Error launching Inspector:** {exc}"

    inspector_url = f"http://localhost:{client_port}"
    return (
        f"**Inspector launched** (PID {_inspector_process.pid})\n\n"
        f"Open the Inspector UI: [{inspector_url}]({inspector_url})\n\n"
        "Select **streamable-http** transport in the Inspector and paste your MCP server URL to connect."
    )


def _stop_inspector() -> str:
    global _inspector_process
    with _inspector_lock:
        if _inspector_process is None or _inspector_process.poll() is not None:
            _inspector_process = None
            return "Inspector is not running."
        pid = _inspector_process.pid
        _inspector_process.terminate()
        try:
            _inspector_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _inspector_process.kill()
        _inspector_process = None
    return f"Inspector (PID {pid}) stopped."


def _inspector_status() -> str:
    with _inspector_lock:
        if _inspector_process is not None and _inspector_process.poll() is None:
            return f"**Running** (PID {_inspector_process.pid})"
        return "**Stopped**"


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------
def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _get_env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y"}


def _normalize_payload_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize common camelCase keys to snake_case expected by MCP speech tools."""
    key_map = {
        "compartmentId": "compartment_id",
        "bucketName": "bucket_name",
        "fileNames": "file_names",
        "jobName": "job_name",
        "modelType": "model_type",
        "languageCode": "language_code",
        "whisperPrompt": "whisper_prompt",
        "diarizationEnabled": "diarization_enabled",
        "outputPrefix": "output_prefix",
    }

    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        normalized[key_map.get(key, key)] = value
    return normalized


# ---------------------------------------------------------------------------
# Interceptors
# ---------------------------------------------------------------------------
async def tracing_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    """Record every MCP tool call with timing, arguments, and result summary."""
    start = time.perf_counter()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "success"
    result_summary = ""

    try:
        result = await handler(request)
    except Exception as exc:
        status = "error"
        result_summary = str(exc)[:500]
        _add_trace({
            "timestamp": ts,
            "tool_name": request.name,
            "args": dict(request.args or {}),
            "result_summary": result_summary,
            "duration_ms": round((time.perf_counter() - start) * 1000),
            "status": status,
        })
        raise

    duration_ms = round((time.perf_counter() - start) * 1000)

    texts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    result_summary = "\n".join(texts).strip()[:500]

    _add_trace({
        "timestamp": ts,
        "tool_name": request.name,
        "args": dict(request.args or {}),
        "result_summary": result_summary,
        "duration_ms": duration_ms,
        "status": status,
    })
    return result


async def payload_to_string_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    """Convert dict payload argument to JSON string for speech tools expecting payload: str."""
    tools_with_string_payload = {
        "create_speech_transcription_job",
        "list_speech_transcription_jobs",
    }

    args = request.args or {}
    payload = args.get("payload")

    if request.name in tools_with_string_payload and payload is not None and not isinstance(payload, str):
        payload_obj: Any = payload
        if isinstance(payload_obj, dict):
            payload_obj = _normalize_payload_keys(payload_obj)

        updated_args = {
            **args,
            "payload": json.dumps(payload_obj),
        }
        logger.debug(
            "Converted payload to JSON string for tool '%s': %s",
            request.name,
            updated_args["payload"],
        )
        request = request.override(args=updated_args)

    return await handler(request)


def build_speech_config() -> dict[str, Any]:
    """Build speech config from environment with sane precedence and defaults."""
    return {
        "compartment_id": _get_env("SPEECH_COMPARTMENT_OCID") or _get_env("COMPARTMENT_ID"),
        "namespace": _get_env("OCI_NAMESPACE"),
        "bucket_name": _get_env("SPEECH_BUCKET"),
        "model_type": _get_env("SPEECH_MODEL_TYPE", "WHISPER_LARGE_V3T"),
        "language_code": _get_env("SPEECH_LANGUAGE_CODE", "auto"),
        "whisper_prompt": _get_env("SPEECH_WHISPER_PROMPT", "This is a customer support conversation."),
        "diarization_enabled": _env_bool("SPEECH_DIARIZATION_ENABLED", True),
    }


# ---------------------------------------------------------------------------
# Initialize LLM
# ---------------------------------------------------------------------------
logger.info("Initializing OCI Generative AI model")
try:
    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=240.0,
    )
    logger.info(
        "GenAI auth mode=%s region=%s",
        auth_mode,
        config.get("region"),
    )
    genai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config=config,
        signer=signer,
        service_endpoint=os.getenv("SERVICE_ENDPOINT"),
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY,
        timeout=(10, 240),
    )
    llm = ChatOCIGenAI(
        client=genai_client,
        model_id=os.getenv("MODEL_ID"),
        service_endpoint=os.getenv("SERVICE_ENDPOINT"),
        compartment_id=os.getenv("COMPARTMENT_ID"),
        model_kwargs={
            "temperature": float(os.getenv("MODEL_TEMPERATURE")),
            "max_tokens": int(os.getenv("MODEL_MAX_TOKENS"))
        },
        provider=os.getenv("PROVIDER"),
    )
    logger.info("LLM initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize LLM: {str(e)}")
    raise

# ---------------------------------------------------------------------------
# Initialize MCP client  (tracing_interceptor runs first, then payload fix)
# ---------------------------------------------------------------------------
logger.info("Initializing MultiServerMCPClient")
try:
    mcp_server_config = build_mcp_server_config(
        mcp_url=os.getenv("MCP_URL"),
        timeout=30.0,
        logger=logger,
    )
    client = MultiServerMCPClient(
        {
            "tools_server": mcp_server_config,
        },
        tool_interceptors=[tracing_interceptor, payload_to_string_interceptor],
    )
    logger.info("Client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize client: {str(e)}")
    raise


# ---------------------------------------------------------------------------
# OCI Object Storage helpers (unchanged)
# ---------------------------------------------------------------------------
def create_object_storage_client() -> oci.object_storage.ObjectStorageClient:
    """Create OCI Object Storage client using shared auth strategy from mcp-server oci_auth."""
    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=120.0,
    )
    logger.info(
        "Object Storage auth mode=%s region=%s",
        auth_mode,
        config.get("region"),
    )
    if signer is not None:
        return oci.object_storage.ObjectStorageClient(config=config, signer=signer)
    return oci.object_storage.ObjectStorageClient(config=config)


def upload_audio_to_bucket(audio_path: str) -> str:
    """Upload audio file to OCI Object Storage and return uploaded object name."""
    speech_config = build_speech_config()
    namespace = speech_config["namespace"]
    bucket_name = speech_config["bucket_name"]
    if not namespace or not bucket_name:
        raise ValueError("Missing OCI namespace or bucket configuration")

    source_path = Path(audio_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    timestamp = int(time.time())
    object_name = f"uploads/{timestamp}_{source_path.name}"
    content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"

    object_storage = create_object_storage_client()
    with source_path.open("rb") as f:
        object_storage.put_object(
            namespace_name=namespace,
            bucket_name=bucket_name,
            object_name=object_name,
            put_object_body=f,
            content_type=content_type,
        )

    logger.info(
        "Uploaded audio file '%s' to bucket '%s' as object '%s'",
        source_path.name,
        bucket_name,
        object_name,
    )
    return object_name


def _extract_tool_text(tool_result: Any) -> str:
    """Extract textual content from MCP call_tool result."""
    texts: list[str] = []
    for block in getattr(tool_result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


async def call_mcp_tool_json(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool, trace the call, and parse its JSON text response."""
    start = time.perf_counter()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "success"
    result_summary = ""

    try:
        async with client.session("tools_server") as session:
            tool_result = await session.call_tool(tool_name, args)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        _add_trace({
            "timestamp": ts,
            "tool_name": tool_name,
            "args": args,
            "result_summary": str(exc)[:500],
            "duration_ms": duration_ms,
            "status": "error",
        })
        raise

    duration_ms = round((time.perf_counter() - start) * 1000)
    raw_text = _extract_tool_text(tool_result)
    result_summary = (raw_text or str(tool_result))[:500]

    _add_trace({
        "timestamp": ts,
        "tool_name": tool_name,
        "args": args,
        "result_summary": result_summary,
        "duration_ms": duration_ms,
        "status": status,
    })

    if not raw_text:
        return {"raw_result": str(tool_result)}

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"raw_result": raw_text}


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


def _build_job_id_tokens(job_id: str) -> list[str]:
    """Build possible job-id tokens for matching output object names."""
    tokens = [job_id]
    if "." in job_id:
        tokens.append(job_id.split(".")[-1])
    return [t for t in tokens if t]


def download_latest_transcription_json(
    namespace: str,
    bucket_name: str,
    prefix: str,
    job_id: str,
) -> tuple[str, str, int, int]:
    """Download the latest JSON result object for a transcription job and return local path."""
    object_storage = create_object_storage_client()
    list_resp = object_storage.list_objects(
        namespace_name=namespace,
        bucket_name=bucket_name,
        prefix=prefix,
    )
    objects = list_resp.data.objects or []
    json_objects = [obj for obj in objects if getattr(obj, "name", "").lower().endswith(".json")]

    if not json_objects:
        raise FileNotFoundError(
            f"No JSON output files found in {namespace}/{bucket_name} with prefix '{prefix}'"
        )

    job_tokens = _build_job_id_tokens(job_id)
    job_matched_json_objects = [
        obj for obj in json_objects
        if any(token in getattr(obj, "name", "") for token in job_tokens)
    ]

    if job_matched_json_objects:
        candidates = job_matched_json_objects
    elif len(json_objects) == 1:
        candidates = json_objects
    else:
        raise FileNotFoundError(
            f"No JSON output object matching job ID '{job_id}' was found under prefix '{prefix}'."
        )

    candidates.sort(
        key=lambda obj: (
            str(getattr(obj, "time_created", "")),
            getattr(obj, "size", 0),
            getattr(obj, "name", ""),
        )
    )
    selected = candidates[-1]
    object_name = selected.name

    get_resp = object_storage.get_object(
        namespace_name=namespace,
        bucket_name=bucket_name,
        object_name=object_name,
    )

    if hasattr(get_resp.data, "content"):
        payload_bytes = get_resp.data.content
    else:
        payload_bytes = get_resp.data.read()

    if isinstance(payload_bytes, str):
        payload_bytes = payload_bytes.encode("utf-8")

    downloads_dir = Path(__file__).parent / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    local_name = f"transcription_{_safe_filename(job_id)}_{Path(object_name).name}"
    local_path = downloads_dir / local_name
    local_path.write_bytes(payload_bytes)

    logger.info("Downloaded transcription JSON object '%s' to '%s'", object_name, str(local_path))
    return str(local_path), object_name, len(candidates), len(json_objects)


async def submit_speech_transcription_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Call MCP speech transcription tool directly with payload."""
    return await call_mcp_tool_json(
        "create_speech_transcription_job",
        {"payload": json.dumps(payload)},
    )


async def get_agent_response(message, history):
    """Process user message and return agent response"""
    logger.info(f"Processing message: {message}")
    try:
        logger.debug("Fetching tools from client")
        tools = await client.get_tools()
        logger.debug(f"Retrieved {len(tools)} tools")

        logger.debug("Creating react agent")
        agent = create_react_agent(llm, tools)

        logger.debug("Invoking agent")
        response = await agent.ainvoke({"messages": message})

        logger.info("Agent response generated successfully")
        return response['messages'][-1].content if isinstance(response['messages'], list) else str(response)
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return f"Error processing request: {str(e)}"


async def chat_interface(message, history):
    """Gradio async chat interface function"""
    logger.debug(f"Chat interface received message: {message}")
    response = await get_agent_response(message, history)
    logger.debug(f"Chat interface returning response: {response}")
    return response


async def upload_and_transcribe(
    audio_file: str | None,
    job_name: str,
    model_type: str,
    language_code: str,
    whisper_prompt: str,
    diarization_enabled: bool,
):
    """Send audio inline to the MCP server and let the server upload + transcribe."""
    if not audio_file:
        return "Please upload an audio file.", None, ""

    try:
        audio_bytes = await asyncio.to_thread(Path(audio_file).read_bytes)
        payload = {
            "file_name": Path(audio_file).name,
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        }

        if job_name and job_name.strip():
            payload["job_name"] = job_name.strip()
        if model_type:
            payload["model_type"] = model_type
        if language_code:
            payload["language_code"] = language_code
        if whisper_prompt and whisper_prompt.strip():
            payload["whisper_prompt"] = whisper_prompt.strip()
        if diarization_enabled:
            payload["diarization_enabled"] = diarization_enabled

        tool_response = await call_mcp_tool("process_audio", {"payload": json.dumps(payload)})
        job_id = tool_response.get("job_id") if isinstance(tool_response, dict) else None
        input_object_name = tool_response.get("input_object_name") if isinstance(tool_response, dict) else None
        transcript = tool_response.get("transcription_text") if isinstance(tool_response, dict) else None

        status = f"Sent `{Path(audio_file).name}` inline to `process_audio`."
        if input_object_name:
            status += f"\n\n**Server uploaded object:** `{input_object_name}`"
        if job_id:
            status += f"\n\n**Job ID:** `{job_id}`"
        if transcript:
            status += f"\n\n**Transcript:** {transcript}"
        return status, tool_response, job_id or ""
    except Exception as e:
        logger.error("Audio transcription submission failed: %s", str(e), exc_info=True)
        return f"Failed to upload/submit transcription: {str(e)}", None, ""


async def check_and_download_transcription(job_id: str):
    """Check job status and download the transcription JSON if job is complete."""
    if not job_id or not job_id.strip():
        return "Please provide a transcription Job ID.", None, None

    clean_job_id = job_id.strip()
    try:
        job_response = await call_mcp_tool_json("get_speech_transcription_job", {"job_id": clean_job_id})
        if "error" in job_response:
            return f"Error: {job_response.get('error')}", job_response, None

        lifecycle_state = (
            job_response.get("lifecycle_state")
            or job_response.get("lifecycleState")
            or ""
        )
        job_details = job_response.get("job") if isinstance(job_response.get("job"), dict) else {}
        if not lifecycle_state:
            lifecycle_state = (
                job_details.get("lifecycle_state")
                or job_details.get("lifecycleState")
                or ""
            )
        lifecycle_state = str(lifecycle_state).upper()

        output_location = job_details.get("output_location") or job_details.get("outputLocation") or {}

        namespace = (
            output_location.get("namespace_name")
            or output_location.get("namespaceName")
            or build_speech_config()["namespace"]
        )
        bucket_name = (
            output_location.get("bucket_name")
            or output_location.get("bucketName")
            or build_speech_config()["bucket_name"]
        )
        prefix = output_location.get("prefix") or ""
        if not prefix:
            job_token = clean_job_id.split(".")[-1] if "." in clean_job_id else clean_job_id
            prefix = f"SpeechJobOutput/job-{job_token}"

        try:
            file_path, object_name, matched_count, total_count = await asyncio.to_thread(
                download_latest_transcription_json,
                namespace,
                bucket_name,
                prefix,
                clean_job_id,
            )
            status = (
                f"Downloaded `{object_name}` from `{namespace}/{bucket_name}` "
                f"using Job ID `{clean_job_id}` (matched {matched_count} of {total_count} JSON object(s) under prefix `{prefix}`). "
                f"Job state: `{'OUTPUT_AVAILABLE (likely SUCCEEDED)' if lifecycle_state in {'', 'UNKNOWN'} else lifecycle_state}`."
            )
            return status, job_response, file_path
        except FileNotFoundError:
            return (
                f"Job `{clean_job_id}` is currently `{lifecycle_state or 'UNKNOWN'}`. "
                "No JSON transcription output found yet. Please retry in a bit.",
                job_response,
                None,
            )
    except Exception as e:
        logger.error("Failed to check/download transcription JSON: %s", str(e), exc_info=True)
        return f"Failed to check/download transcription JSON: {str(e)}", None, None


# ---------------------------------------------------------------------------
# Trace tab helpers
# ---------------------------------------------------------------------------
def _trace_count_label() -> str:
    count = len(_get_traces())
    if count == 0:
        return "No tool calls recorded yet."
    return f"**{count}** tool call(s) recorded."


def _refresh_traces():
    """Return trace data formatted for the Dataframe and the latest trace detail."""
    traces = _get_traces()
    label = _trace_count_label()
    if not traces:
        return label, [], None

    rows = []
    for t in reversed(traces):
        rows.append([
            t.get("timestamp", ""),
            t.get("tool_name", ""),
            t.get("duration_ms", 0),
            t.get("status", ""),
            (t.get("result_summary") or "")[:120],
        ])

    latest = traces[-1] if traces else None
    return label, rows, latest


def _clear_traces_ui():
    _clear_traces()
    return _trace_count_label(), [], None


def _select_trace(evt: gr.SelectData):
    """When user clicks a row in the Dataframe, show that trace's full detail."""
    traces = _get_traces()
    reversed_traces = list(reversed(traces))
    idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    if 0 <= idx < len(reversed_traces):
        return reversed_traces[idx]
    return None


def _auto_refresh_trace_count():
    """Lightweight poll that updates only the counter label."""
    return _trace_count_label()


# ---------------------------------------------------------------------------
# Inspector tab helpers
# ---------------------------------------------------------------------------
def _on_launch_inspector(server_url: str, client_port: str, server_port: str):
    c_port = int(client_port) if client_port.strip().isdigit() else 6274
    s_port = int(server_port) if server_port.strip().isdigit() else 6277
    result = _launch_inspector(client_port=c_port, server_port=s_port)
    return result, _inspector_status()


def _on_stop_inspector():
    result = _stop_inspector()
    return result, _inspector_status()


def _on_refresh_status():
    return _inspector_status()


# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
_CUSTOM_CSS = """
.app-header {
    text-align: center;
    padding: 1.5rem 1rem 0.5rem;
}
.app-header h1 {
    margin-bottom: 0.25rem;
}
.app-subtitle {
    text-align: center;
    opacity: 0.7;
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 1.05rem;
}
.trace-dataframe {
    max-height: 420px;
    overflow-y: auto;
}
.inspector-status-badge {
    font-size: 1rem;
    padding: 0.5rem 1rem;
    border-radius: 8px;
}
"""


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
def main():
    """Create and launch Gradio UI"""
    logger.info("Starting Gradio UI")
    try:
        speech_config = build_speech_config()

        with gr.Blocks(
            title="AI Agent Console",
            theme=gr.themes.Soft(),
            css=_CUSTOM_CSS,
        ) as interface:

            # ── Header ──
            gr.Markdown(
                "# AI Agent Console",
                elem_classes=["app-header"],
            )
            gr.Markdown(
                "Interact with your AI agent, inspect MCP tool calls, manage speech transcriptions, and launch the MCP Inspector.",
                elem_classes=["app-subtitle"],
            )

            # ================================================================
            # Tab 1: Chat
            # ================================================================
            with gr.Tab("Chat", id="tab-chat"):
                chat_ui = gr.ChatInterface(
                    fn=chat_interface,
                    title="",
                    description="Chat with the AI agent powered by OCI Generative AI. The agent can call MCP tools on your behalf.",
                    examples=[
                        "Analyze the sentiment of this text: 'What's in a name? That which we call a rose by any other word would smell as sweet.'",
                        "Tell me a joke",
                    ],
                    cache_examples=False,
                )

            # ================================================================
            # Tab 2: MCP Tool Traces
            # ================================================================
            with gr.Tab("MCP Tool Traces", id="tab-traces"):
                gr.Markdown("### MCP Tool Call Traces")
                gr.Markdown(
                    "Every MCP tool call made by the agent or the transcription tab is "
                    "logged here with timing, arguments, and a result summary. "
                    "The counter auto-updates; click **Refresh** to load the full table."
                )

                trace_count_display = gr.Markdown(
                    value=_trace_count_label(),
                )

                with gr.Row():
                    refresh_traces_btn = gr.Button("Refresh", variant="primary", scale=1)
                    clear_traces_btn = gr.Button("Clear All", variant="stop", scale=1)

                trace_table = gr.Dataframe(
                    headers=["Timestamp", "Tool", "Duration (ms)", "Status", "Result Preview"],
                    datatype=["str", "str", "number", "str", "str"],
                    interactive=False,
                    wrap=True,
                    elem_classes=["trace-dataframe"],
                )

                gr.Markdown("#### Selected Trace Detail")
                trace_detail = gr.JSON(label="Full trace (click a row above)")

                # Auto-poll the trace count every 3 seconds
                trace_timer = gr.Timer(value=3)
                trace_timer.tick(
                    fn=_auto_refresh_trace_count,
                    inputs=[],
                    outputs=[trace_count_display],
                )

                refresh_traces_btn.click(
                    fn=_refresh_traces,
                    inputs=[],
                    outputs=[trace_count_display, trace_table, trace_detail],
                )
                clear_traces_btn.click(
                    fn=_clear_traces_ui,
                    inputs=[],
                    outputs=[trace_count_display, trace_table, trace_detail],
                )
                trace_table.select(
                    fn=_select_trace,
                    inputs=[],
                    outputs=[trace_detail],
                )

            # ================================================================
            # Tab 3: Audio Transcription
            # ================================================================
            with gr.Tab("Audio Transcription", id="tab-transcription"):
                gr.Markdown(
                    f"Upload an audio file and click **Submit** to create a speech transcription job.\n\n"
                    f"**Target Bucket:** `{speech_config.get('namespace') or '<unset>'}/{speech_config.get('bucket_name') or '<unset>'}`"
                )

                audio_file = gr.File(
                    label="Audio file",
                    type="filepath",
                    file_types=[".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"],
                )

                with gr.Accordion("Transcription options", open=False):
                    with gr.Row():
                        job_name = gr.Textbox(
                            label="Job name (optional)",
                            placeholder="CustomerCallTranscription",
                            scale=2,
                        )
                        model_type = gr.Dropdown(
                            label="Model type",
                            choices=["ORACLE", "WHISPER_MEDIUM", "WHISPER_LARGE_V2", "WHISPER_LARGE_V3T"],
                            value=speech_config["model_type"],
                            scale=1,
                        )
                    with gr.Row():
                        language_code = gr.Textbox(
                            label="Language code",
                            value=speech_config["language_code"],
                            scale=1,
                        )
                        whisper_prompt = gr.Textbox(
                            label="Whisper prompt",
                            value=speech_config["whisper_prompt"],
                            scale=2,
                        )
                    diarization_enabled = gr.Checkbox(
                        label="Enable speaker diarization",
                        value=speech_config["diarization_enabled"],
                    )

                submit_btn = gr.Button("Submit Transcription Job", variant="primary")
                status_output = gr.Markdown(label="Status")
                result_output = gr.JSON(label="MCP tool response")
                job_id_output = gr.Textbox(
                    label="Transcription Job ID",
                    placeholder="Will be auto-filled after submission",
                )

                submit_btn.click(
                    fn=upload_and_transcribe,
                    inputs=[
                        audio_file,
                        job_name,
                        model_type,
                        language_code,
                        whisper_prompt,
                        diarization_enabled,
                    ],
                    outputs=[status_output, result_output, job_id_output],
                )

                gr.Markdown("---")
                gr.Markdown("### Download Transcription JSON")
                check_download_btn = gr.Button("Check Status & Download JSON", variant="secondary")
                download_status_output = gr.Markdown(label="Download status")
                job_details_output = gr.JSON(label="Job details")
                downloaded_file_output = gr.File(label="Downloaded transcription JSON")

                check_download_btn.click(
                    fn=check_and_download_transcription,
                    inputs=[job_id_output],
                    outputs=[
                        download_status_output,
                        job_details_output,
                        downloaded_file_output,
                    ],
                )

            # ================================================================
            # Tab 4: MCP Inspector
            # ================================================================
            with gr.Tab("MCP Inspector", id="tab-inspector"):
                gr.Markdown("### MCP Inspector")
                gr.Markdown(
                    "Launch the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) "
                    "to interactively test and debug any MCP server. The Inspector opens in a "
                    "separate browser tab where you can select `streamable-http` transport and "
                    "paste your server URL."
                )

                with gr.Row():
                    inspector_url_input = gr.Textbox(
                        label="MCP Server URL (for reference)",
                        value=mcp_url or "",
                        placeholder="http://localhost:8000/mcp",
                        scale=3,
                        info="This URL is shown for your convenience. Paste it into the Inspector UI after launch.",
                    )
                with gr.Row():
                    inspector_client_port = gr.Textbox(
                        label="Inspector UI port",
                        value="6274",
                        scale=1,
                    )
                    inspector_server_port = gr.Textbox(
                        label="Inspector proxy port",
                        value="6277",
                        scale=1,
                    )

                with gr.Row():
                    launch_inspector_btn = gr.Button("Launch Inspector", variant="primary", scale=1)
                    stop_inspector_btn = gr.Button("Stop Inspector", variant="stop", scale=1)
                    refresh_status_btn = gr.Button("Refresh Status", variant="secondary", scale=1)

                inspector_output = gr.Markdown(label="Inspector output")
                inspector_status_display = gr.Markdown(
                    value=_inspector_status(),
                    label="Inspector status",
                    elem_classes=["inspector-status-badge"],
                )

                launch_inspector_btn.click(
                    fn=_on_launch_inspector,
                    inputs=[inspector_url_input, inspector_client_port, inspector_server_port],
                    outputs=[inspector_output, inspector_status_display],
                )
                stop_inspector_btn.click(
                    fn=_on_stop_inspector,
                    inputs=[],
                    outputs=[inspector_output, inspector_status_display],
                )
                refresh_status_btn.click(
                    fn=_on_refresh_status,
                    inputs=[],
                    outputs=[inspector_status_display],
                )

            # ── Footer ──
            gr.Markdown(
                "<div style='text-align:center; opacity:0.5; margin-top:1.5rem; font-size:0.85rem;'>"
                "AI Agent Console &mdash; Powered by OCI Generative AI &amp; MCP"
                "</div>"
            )

        logger.info("Launching Gradio interface")
        interface.launch(
            server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
            server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        )
        logger.info("Gradio interface launched successfully")
    except Exception as e:
        logger.error(f"Failed to launch Gradio UI: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
