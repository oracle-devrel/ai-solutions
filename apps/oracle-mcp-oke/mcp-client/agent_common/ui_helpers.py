from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import gradio as gr

from .config import AUDIO_EXTENSIONS


def is_audio_file(path: str) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def extract_file_paths(files: list[Any]) -> list[str]:
    out: list[str] = []
    for entry in files:
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict):
            out.append(str(entry.get("path") or entry.get("name") or ""))
    return [p for p in out if p]


def working_message(text: str) -> str:
    safe = html.escape(str(text or "").strip())
    return (
        "<div class='working-inline'>"
        "  <span class='working-spinner'></span>"
        f"  <span class='working-text'>{safe}</span>"
        "  <span class='working-dots'><span></span><span></span><span></span></span>"
        "</div>"
    )


def choice_updates(state: dict[str, Any]) -> tuple[gr.Markdown, gr.Markdown, list[gr.Button], gr.Dropdown, gr.Button]:
    choice = state.get("pending_choice")
    if not choice:
        return (
            gr.Markdown(value="", visible=False),
            gr.Markdown(value="", visible=False),
            [gr.Button(visible=False) for _ in range(5)],
            gr.Dropdown(choices=[], value=None, visible=False),
            gr.Button(visible=False),
        )

    options = choice.get("options", [])[:5]
    notice = f"**Selection needed:** {choice.get('prompt', 'Choose one option')}"
    detail = "\n".join(f"{index + 1}. `{opt.get('label', '')}`" for index, opt in enumerate(options))
    buttons: list[gr.Button] = []
    for index in range(5):
        if index < len(options):
            buttons.append(gr.Button(value=options[index]["label"], visible=True, variant="secondary", size="sm"))
        else:
            buttons.append(gr.Button(visible=False))

    labels = [opt.get("label", "") for opt in options]
    return (
        gr.Markdown(value=notice, visible=True),
        gr.Markdown(value=detail, visible=True),
        buttons,
        gr.Dropdown(choices=labels, value=(labels[0] if labels else None), visible=True, interactive=True),
        gr.Button(value="Apply Selection", visible=True, variant="primary", size="sm"),
    )


def activity_markdown(_: dict[str, Any]) -> gr.Markdown:
    return gr.Markdown(value="", visible=False)