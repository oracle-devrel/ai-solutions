import contextvars
import threading
from typing import Any


CURRENT_INTENT_ID: contextvars.ContextVar[str] = contextvars.ContextVar("current_intent_id", default="")

_TOOL_CALL_TRACES: list[dict[str, Any]] = []
_TRACE_LOCK = threading.Lock()
_MAX_TRACES = 500

_PENDING_UPLOADED_OBJECTS: list[str] = []
_PENDING_UPLOAD_LOCK = threading.Lock()

_PROGRESS_EVENTS: list[dict[str, Any]] = []
_PROGRESS_LOCK = threading.Lock()
_PROGRESS_MILESTONES: dict[str, int] = {}

_ACTIVITY_EVENTS: list[dict[str, Any]] = []
_ACTIVITY_LOCK = threading.Lock()

_TOOL_ACTION_MAP = {
    "upload_audio_to_bucket": "Uploading audio file",
    "process_audio": "Processing audio transcription",
    "create_speech_transcription_job": "Creating transcription job",
    "get_speech_transcription_job": "Checking job status",
    "cancel_speech_transcription_job": "Canceling transcription job",
    "list_speech_transcription_jobs": "Listing transcription jobs",
    "get_speech_transcription_text": "Fetching transcript text",
    "read_transcription_result": "Reading transcription result",
    "find_transcription_job_by_filename": "Finding job by filename",
    "find_transcription_job_by_object": "Finding job by object",
    "sentiment_analysis": "Analyzing sentiment",
    "list_bucket_audio_files": "Listing bucket audio files",
}


def add_trace(entry: dict[str, Any]) -> None:
    with _TRACE_LOCK:
        _TOOL_CALL_TRACES.append(entry)
        if len(_TOOL_CALL_TRACES) > _MAX_TRACES:
            del _TOOL_CALL_TRACES[: len(_TOOL_CALL_TRACES) - _MAX_TRACES]


def get_traces() -> list[dict[str, Any]]:
    with _TRACE_LOCK:
        return list(_TOOL_CALL_TRACES)


def get_traces_for_intent(intent_id: str, start_index: int = 0) -> list[dict[str, Any]]:
    traces = get_traces()
    sliced = traces[start_index:] if start_index > 0 else traces
    return [t for t in sliced if str(t.get("intent_id", "")) == str(intent_id)]


def clear_traces() -> None:
    with _TRACE_LOCK:
        _TOOL_CALL_TRACES.clear()


def push_pending_uploaded_object(object_name: str) -> None:
    name = str(object_name or "").strip()
    if not name:
        return
    with _PENDING_UPLOAD_LOCK:
        if name not in _PENDING_UPLOADED_OBJECTS:
            _PENDING_UPLOADED_OBJECTS.append(name)
        if len(_PENDING_UPLOADED_OBJECTS) > 20:
            del _PENDING_UPLOADED_OBJECTS[: len(_PENDING_UPLOADED_OBJECTS) - 20]


def pop_pending_uploaded_objects() -> list[str]:
    with _PENDING_UPLOAD_LOCK:
        items = list(_PENDING_UPLOADED_OBJECTS)
        _PENDING_UPLOADED_OBJECTS.clear()
    return items


def shift_pending_uploaded_object() -> str:
    with _PENDING_UPLOAD_LOCK:
        if not _PENDING_UPLOADED_OBJECTS:
            return ""
        return str(_PENDING_UPLOADED_OBJECTS.pop(0) or "").strip()


def add_progress_event(entry: dict[str, Any]) -> None:
    with _PROGRESS_LOCK:
        _PROGRESS_EVENTS.append(entry)
        if len(_PROGRESS_EVENTS) > 200:
            del _PROGRESS_EVENTS[: len(_PROGRESS_EVENTS) - 200]


def latest_progress_text() -> str:
    with _PROGRESS_LOCK:
        if not _PROGRESS_EVENTS:
            return ""
        event = _PROGRESS_EVENTS[-1]
    tool_name = str(event.get("tool_name") or "")
    progress = event.get("progress")
    total = event.get("total")
    message = str(event.get("message") or "").strip()
    if progress is None or total in (None, 0):
        return message or (f"{tool_name}: running" if tool_name else "running")
    try:
        pct = int((float(progress) / float(total)) * 100.0)
    except Exception:
        pct = 0
    if message:
        return f"{message} ({pct}%)"
    if tool_name:
        return f"{tool_name}: {pct}%"
    return f"{pct}%"


def clear_progress_events() -> None:
    with _PROGRESS_LOCK:
        _PROGRESS_EVENTS.clear()
        _PROGRESS_MILESTONES.clear()


def should_emit_progress_marker(intent_id: str, tool_name: str, pct: int) -> int:
    marker_key = f"{intent_id}:{tool_name}"
    marker = 0
    for step in (10, 25, 50, 75, 100):
        if pct >= step:
            marker = step
    if not marker:
        return 0
    with _PROGRESS_LOCK:
        last_marker = int(_PROGRESS_MILESTONES.get(marker_key, 0))
        if marker > last_marker:
            _PROGRESS_MILESTONES[marker_key] = marker
            return marker
    return 0


def add_activity_event(entry: dict[str, Any]) -> None:
    with _ACTIVITY_LOCK:
        _ACTIVITY_EVENTS.append(entry)
        if len(_ACTIVITY_EVENTS) > 240:
            del _ACTIVITY_EVENTS[: len(_ACTIVITY_EVENTS) - 240]


def get_recent_activity(intent_id: str, limit: int = 5) -> list[dict[str, Any]]:
    with _ACTIVITY_LOCK:
        events = list(_ACTIVITY_EVENTS)
    if intent_id:
        events = [event for event in events if str(event.get("intent_id") or "") == intent_id]
    return events[-limit:]


def clear_activity_events() -> None:
    with _ACTIVITY_LOCK:
        _ACTIVITY_EVENTS.clear()
    with _PROGRESS_LOCK:
        _PROGRESS_MILESTONES.clear()


def human_tool_action(tool_name: str) -> str:
    return _TOOL_ACTION_MAP.get(tool_name, "Running MCP step")
