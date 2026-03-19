from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import VALID_JOB_OCID_RE


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def merge_unique_str_list(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        val = str(item or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def valid_job_id(job_id: str) -> bool:
    value = (job_id or "").strip().rstrip(".,;:)]}")
    return bool(value and VALID_JOB_OCID_RE.match(value))


def default_session_state() -> dict[str, Any]:
    return {
        "jobs_by_id": {},
        "jobs_by_file": {},
        "job_ids_by_file": {},
        "job_id_by_uploaded_object": {},
        "uploaded_objects_by_file": {},
        "file_by_uploaded_object": {},
        "downloaded_result_by_job_id": {},
        "latest_job_id": "",
        "transcript_cache_by_job_id": {},
        "sentiment_cache_by_job_id": {},
        "pending_choice": None,
        "pending_action": None,
        "last_sentiment_result": None,
        "memory_loaded": False,
        "show_flash_actions": True,
        "active_intent_id": "",
    }


def sanitize_job_memory(state: dict[str, Any]) -> None:
    jobs_by_id = state.get("jobs_by_id") if isinstance(state.get("jobs_by_id"), dict) else {}
    valid_job_ids = {job_id for job_id in jobs_by_id.keys() if valid_job_id(str(job_id))}
    for job_id in list(jobs_by_id.keys()):
        if job_id not in valid_job_ids:
            del jobs_by_id[job_id]

    jobs_by_file = state.get("jobs_by_file") if isinstance(state.get("jobs_by_file"), dict) else {}
    for source_file, job_id in list(jobs_by_file.items()):
        if not valid_job_id(str(job_id)):
            del jobs_by_file[source_file]

    job_ids_by_file = state.get("job_ids_by_file") if isinstance(state.get("job_ids_by_file"), dict) else {}
    for source_file, job_ids in list(job_ids_by_file.items()):
        if not isinstance(job_ids, list):
            job_ids_by_file[source_file] = []
            continue
        filtered = [str(job_id) for job_id in job_ids if valid_job_id(str(job_id))]
        job_ids_by_file[source_file] = merge_unique_str_list(filtered)

    job_id_by_uploaded_object = state.get("job_id_by_uploaded_object") if isinstance(state.get("job_id_by_uploaded_object"), dict) else {}
    for object_name, job_id in list(job_id_by_uploaded_object.items()):
        if not valid_job_id(str(job_id)):
            del job_id_by_uploaded_object[object_name]

    downloaded_result_by_job_id = state.get("downloaded_result_by_job_id") if isinstance(state.get("downloaded_result_by_job_id"), dict) else {}
    for job_id in list(downloaded_result_by_job_id.keys()):
        if not valid_job_id(str(job_id)):
            del downloaded_result_by_job_id[job_id]

    transcript_cache_by_job_id = state.get("transcript_cache_by_job_id") if isinstance(state.get("transcript_cache_by_job_id"), dict) else {}
    for job_id in list(transcript_cache_by_job_id.keys()):
        if not valid_job_id(str(job_id)):
            del transcript_cache_by_job_id[job_id]

    latest = str(state.get("latest_job_id") or "")
    if not valid_job_id(latest):
        state["latest_job_id"] = ""


def ensure_state(state: dict[str, Any] | None) -> dict[str, Any]:
    base = default_session_state()
    state = state or {}
    for key, value in base.items():
        state.setdefault(key, value)

    if not state.get("memory_loaded"):
        sanitize_job_memory(state)
        state["memory_loaded"] = True

    return state


def context_markdown(state: dict[str, Any], short_text) -> str:
    latest = state.get("latest_job_id") or "<none>"
    latest_short = latest if latest == "<none>" else f"`{short_text(latest, 56)}`"
    files = sorted((state.get("jobs_by_file") or {}).keys())
    jobs = state.get("jobs_by_id") or {}
    transcripts = state.get("transcript_cache_by_job_id") or {}
    return "\n".join(
        [
            "### Context",
            f"- Latest job: {latest_short}",
            f"- Known jobs: **{len(jobs)}**",
            f"- Cached transcripts: **{len(transcripts)}**",
            f"- Known source files: **{len(files)}**",
            "- File samples: " + (", ".join(f"`{Path(name).name}`" for name in files[:5]) if files else "<none>"),
        ]
    )


def save_job(
    state: dict[str, Any],
    job_id: str,
    *,
    display_name: str = "",
    status: str = "",
    source_file: str = "",
    uploaded_object: str = "",
) -> None:
    if not job_id:
        return
    record = state["jobs_by_id"].setdefault(job_id, {})
    if display_name:
        record["display_name"] = display_name
    if status:
        record["status"] = status
    record["last_seen"] = now_ts()

    if source_file:
        state["jobs_by_file"][source_file] = job_id
        ids = state["job_ids_by_file"].setdefault(source_file, [])
        if job_id not in ids:
            ids.append(job_id)
        record["source_files"] = merge_unique_str_list(record.get("source_files", []) + [source_file])

    if uploaded_object:
        record["uploaded_objects"] = merge_unique_str_list(record.get("uploaded_objects", []) + [uploaded_object])

    state["latest_job_id"] = job_id