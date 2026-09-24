"""Interactive OCI Generative AI Sandbox tutorial, served by Streamlit."""

from __future__ import annotations

import os
import json
import time
import hmac
import secrets
import sqlite3
import string
import threading
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from streamlit.runtime.scriptrunner import get_script_run_ctx

from services.oci_openai import OciOpenAIConfig, run_prompt
from services.oci_sandbox import run_hybrid_web_research, run_langgraph_research, run_package_model_artifact, run_single_turn

# The launcher resolves .env values before Streamlit starts. Do not replace its
# generated APP_PASSWORD during a Streamlit script rerun.
load_dotenv()

st.set_page_config(page_title="OCI Sandbox Lab", page_icon="◈", layout="wide")

DEFAULT_COMPARTMENT = "ocid1.compartment.oc1..aaaaaaaa75igkvdlzgwy5kly2cyjysezlkmsw436b3uvjeir4mffyz2k2dyq"
ACTIVE_SESSION_TTL_SECONDS = 120
PRESENCE_DB_PATH = Path(
    os.getenv("PRESENCE_DB_PATH", str(Path(__file__).parent / "deployment-local" / "presence.sqlite3"))
)
APP_STARTED_AT_UTC = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
_presence_lock = threading.Lock()


def app_credentials() -> tuple[str, str]:
    """Return the configured login credentials, generating a startup password if needed."""
    username = os.getenv("APP_USER") or "oci"
    password = os.getenv("APP_PASSWORD")
    if not password:
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(16))
        # Store it in the running process so Streamlit reruns do not rotate it.
        os.environ["APP_PASSWORD"] = password
        print(
            "APP_PASSWORD was not set. Generated startup login password: "
            f"{password}",
            flush=True,
        )
    return username, password


def current_session_id() -> str:
    """Return Streamlit's server-side session ID, with a safe local fallback."""
    context = get_script_run_ctx(suppress_warning=True)
    if context and context.session_id:
        return context.session_id
    if "presence_session_id" not in st.session_state:
        st.session_state.presence_session_id = secrets.token_urlsafe(16)
    return st.session_state.presence_session_id


def record_presence() -> tuple[int, int]:
    """Persist this session and return active and total visitor counts."""
    session_id = current_session_id()
    now = time.time()
    with _presence_lock:
        PRESENCE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(PRESENCE_DB_PATH, timeout=5) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS visitors (session_id TEXT PRIMARY KEY, first_seen REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS active_sessions (session_id TEXT PRIMARY KEY, last_seen REAL NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO visitors (session_id, first_seen) VALUES (?, ?)", (session_id, now)
            )
            connection.execute(
                "INSERT INTO active_sessions (session_id, last_seen) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET last_seen = excluded.last_seen",
                (session_id, now),
            )
            connection.execute("DELETE FROM active_sessions WHERE last_seen < ?", (now - ACTIVE_SESSION_TTL_SECONDS,))
            active_users = connection.execute("SELECT COUNT(*) FROM active_sessions").fetchone()[0]
            visited_users = connection.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
        return active_users, visited_users


def remove_presence() -> None:
    """Remove this session from the active-user count on logout."""
    with _presence_lock:
        if not PRESENCE_DB_PATH.exists():
            return
        with sqlite3.connect(PRESENCE_DB_PATH, timeout=5) as connection:
            connection.execute("DELETE FROM active_sessions WHERE session_id = ?", (current_session_id(),))


APP_USER, APP_PASSWORD = app_credentials()


def value(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback)


def require_login() -> None:
    """Show the login screen and stop rendering until this browser session authenticates."""
    if st.session_state.get("authenticated"):
        return

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, login_column, _ = st.columns((1, 1.2, 1))
    with login_column:
        st.title("OCI Sandbox Lab")
        st.caption("Sign in to access the tutorial workspace.")
        with st.form("login_form"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            valid_username = hmac.compare_digest(username, APP_USER)
            valid_password = hmac.compare_digest(password, APP_PASSWORD)
            if valid_username and valid_password:
                st.session_state.authenticated = True
                st.rerun()
            st.error("Invalid username or password.")

    st.stop()


def console_entry_type(event: str) -> tuple[str, str]:
    if event.startswith("OCI SDK → run_sandbox_command"):
        return "command", "▶ Command"
    if "← command exit" in event or event.startswith(("Local executor ←", "Local planner output", "Local reviewer output")):
        return "output", "↳ Output"
    if event.startswith("ERROR:"):
        return "output", "⚠ Error"
    return "activity", "● Activity"


def console_markup(entries: list[str], element_id: str) -> str:
    cards = []
    for item in entries:
        style, label = console_entry_type(item)
        cards.append(f'<div class="execution-entry {style}"><span class="execution-label">{label}</span>{escape(item)}</div>')
    content = "".join(cards) or "<span class=\"execution-label\">Ready</span>No execution events have arrived yet."
    return (
        f'<div id="{element_id}" class="live-log">{content}</div>'
        f'<script>const c=document.getElementById("{element_id}"); if(c) c.scrollTop=c.scrollHeight;</script>'
    )


def timed_event(event: str, elapsed_seconds: float) -> str:
    """Keep the raw event prefix intact while showing elapsed work in the console."""
    return f"{event}\n⏱ Step time: {elapsed_seconds:.2f}s"


def apply_oracle_theme() -> None:
    st.markdown(
        """
        <style>
        :root { --oracle-red: #c74634; --ink: #172033; --mist: #f4f6f9; --line: #d7dce5; --navy: #101827; }
        .stApp { background: var(--mist); color: var(--ink); }
        [data-testid="stSidebar"] { background: var(--navy); }
        [data-testid="stSidebar"] * { color: #f8f7f5 !important; }
        [data-testid="stSidebar"] input { color: #161513 !important; background: #fff !important; }
        .hero { align-items: center; background: linear-gradient(110deg, #101827, #253552); border-left: 7px solid var(--oracle-red); color: #fff;
                 display: flex; gap: 2rem; justify-content: space-between; padding: 2.3rem 2.6rem 2.1rem; margin: .3rem 0 1.7rem; }
        .hero-copy { max-width: 47rem; }
        .eyebrow { color: #f3695a; font-size: .78rem; font-weight: 700; letter-spacing: .13em;
                   text-transform: uppercase; margin-bottom: .6rem; }
        .hero h1 { font-size: 2.65rem; line-height: 1.06; margin: 0 0 .7rem; color: #fff; }
        .hero p { color: #dedad5; font-size: 1.08rem; margin: 0; }
        .presence-panel { background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.28); border-radius: 6px; min-width: 176px; padding: .85rem 1rem; }
        .presence-title { color: #dedad5; font: 700 .66rem/1.3 Inter, sans-serif; letter-spacing: .1em; text-transform: uppercase; }
        .presence-values { color: #fff; font: 700 1rem/1.65 Inter, sans-serif; white-space: nowrap; }
        .step-card { background: #fff; border: 1px solid var(--line); border-radius: 4px; border-top: 4px solid var(--oracle-red);
                     min-height: 154px; padding: 1.15rem 1.15rem .85rem; margin-bottom: 1.25rem; box-shadow: 0 2px 6px rgba(16,24,39,.05); }
        .step-number { color: var(--oracle-red); font-weight: 800; font-size: .8rem; letter-spacing: .1em; }
        .step-card h3 { margin: .35rem 0 .45rem; font-size: 1.12rem; }
        .step-card p { color: #59544f; font-size: .92rem; }
        .run-badge { background: #e6f4ea; border-radius: 99px; color: #176b3a; display: inline-block;
                     font-size: .7rem; font-weight: 750; letter-spacing: .07em; padding: .22rem .5rem; text-transform: uppercase; }
        .label-chip { background: #eef1f6; border: 1px solid #d7dce5; border-radius: 99px; color: #40506a; display: inline-block;
                      font: 650 .69rem/1.1 Inter, sans-serif; margin: .1rem .22rem .35rem 0; padding: .25rem .48rem; }
        .stButton > button[kind="primary"] { background: var(--oracle-red); border-color: var(--oracle-red); }
        .stTabs [data-baseweb="tab"] { font-weight: 650; }
        .stTabs [aria-selected="true"] { color: var(--oracle-red); }
        .tutorial-heading { border-bottom: 1px solid var(--line); margin: .5rem 0 1.2rem; padding-bottom: .75rem; }
        .tutorial-heading h2 { color: var(--ink); font-size: 1.9rem; margin: .25rem 0; }
        .session-card { background: #fff; border: 1px solid var(--line); padding: 1.15rem; margin: .6rem 0; }
        .session-card h4 { color: var(--oracle-red); font-size: .78rem; letter-spacing: .09em; margin: 0 0 .7rem; text-transform: uppercase; }
        .live-log { background: #0b1020; border: 1px solid #253552; border-radius: 4px; color: #f4f6f9;
                    font: .82rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; height: 350px;
                    overflow-y: scroll; scrollbar-gutter: stable; padding: 1rem; scroll-behavior: smooth; }
        .live-log::-webkit-scrollbar { width: 10px; }
        .live-log::-webkit-scrollbar-track { background: #0b1020; }
        .live-log::-webkit-scrollbar-thumb { background: #596579; border-radius: 8px; }
        .execution-entry { border-left: 3px solid #596579; margin: 0 0 1rem; padding: .65rem .8rem; white-space: pre-wrap; }
        .execution-entry.command { border-left-color: #d66a57; background: #171d2c; }
        .execution-entry.output { border-left-color: #5dbb8a; background: #101d20; }
        .execution-entry.activity { border-left-color: #6797d6; background: #111827; }
        .execution-label { color: #c8d5e8; display: block; font: 700 .7rem/1.3 Inter, sans-serif; letter-spacing: .08em; margin-bottom: .35rem; text-transform: uppercase; }
        .st-key-logout button { font-size: 1.35rem; line-height: 1; min-height: 2.35rem; padding: .25rem .6rem; }
        .app-footer { border-top: 1px solid var(--line); color: #596579; font: 600 .76rem/1.4 Inter, sans-serif; margin-top: 2rem; padding: 1rem 0; text-align: right; }
        .console-copy { background: #fff; border: 1px solid #b9c2d0; border-radius: 4px; color: #172033 !important; cursor: pointer; display: block;
                            font: 600 .88rem/1.2 Inter, sans-serif; padding: .55rem .65rem; text-align: center; text-decoration: none; }
        .console-copy:hover { border-color: var(--oracle-red); color: var(--oracle-red) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    require_login()
    apply_oracle_theme()
    active_users, visited_users = record_presence()

    with st.sidebar:
        st.markdown("### OCI Sandbox Lab")
        st.caption("Tutorial workspace · local configuration")
        st.divider()
        st.markdown("**Connection settings**")
        region = st.text_input("Region", value=value("OCI_REGION", "us-chicago-1"))
        compartment_id = st.text_input(
            "Compartment OCID", value=value("OCI_COMPARTMENT_ID", DEFAULT_COMPARTMENT)
        )
        project_id = st.text_input(
            "Generative AI Project OCID",
            value=value("OCI_SANDBOX_PROJECT_ID"),
            key="sandbox_project_id",
        )
        model = st.text_input("Validation model", value=value("OCI_MODEL_ID", "openai.gpt-oss-120b"))
        artifact_model = st.text_input(
            "Artifact model", value=value("OCI_ARTIFACT_MODEL_ID", value("OCI_MODEL_ID", "openai.gpt-oss-120b"))
        )
        api_key = st.text_input(
            "OCI Generative AI API key", value=value("OCI_GENAI_API_KEY"), type="password"
        )
        st.caption("Credentials stay in this browser session and are never saved by the app.")

    _, logout_column = st.columns((11, 1))
    with logout_column:
        if st.button("⏻", key="logout", help="Log out", use_container_width=True):
            remove_presence()
            st.session_state.pop("authenticated", None)
            st.rerun()

    st.markdown(
        """
        <section class="hero">
          <div class="hero-copy">
            <div class="eyebrow">Oracle Cloud Infrastructure</div>
            <h1>GenAI Sandbox Lab</h1>
            <p>Build confidence with OCI sandbox concepts through short, hands-on tutorials—then validate that your project can reach an OCI-hosted model.</p>
          </div>
          <aside class="presence-panel" aria-label="Visitor activity">
            <div class="presence-title">Visitor activity</div>
            <div class="presence-values">👥 {active_users} online<br>👀 {visited_users} visited</div>
          </aside>
        </section>
        """.format(active_users=active_users, visited_users=visited_users),
        unsafe_allow_html=True,
    )

    tutorial, overview, validate, resources = st.tabs(
        ["⭐ Sandbox tutorial", "Overview", "Validate access", "Resources"]
    )

    with overview:
        st.subheader("A clear path from setup to a safe experiment")
        first, second, third = st.columns(3)
        cards = [
            ("01 · PREPARE", "Choose the boundary", "Use a dedicated compartment and Generative AI project. These define ownership, access, and billing scope."),
            ("02 · SANDBOX", "Create a disposable workspace", "Provision a GenAI Sandbox for an isolated, short-lived experiment. Keep secrets and application work outside the sandbox image."),
            ("03 · VALIDATE", "Prove the connection", "Send a small test request to an OCI-hosted model before moving on to a larger sandbox tutorial."),
        ]
        for column, (number, heading, copy) in zip((first, second, third), cards):
            with column:
                st.markdown(
                    f'<div class="step-card"><div class="step-number">{number}</div><h3>{heading}</h3><p>{copy}</p></div>',
                    unsafe_allow_html=True,
                )
        st.subheader("What is an OCI GenAI Sandbox?")
        st.write(
            "An OCI GenAI Sandbox is a temporary, private cloud workspace where you can safely run code. "
            "It includes a Linux shell, files, and controlled network access, so an AI agent or user can run commands, "
            "create files, and continue working during the same session."
        )
        st.write(
            "Each sandbox is created when you need it, can be reconnected to using its ID, and is kept separate from "
            "your main application and other users."
        )

        st.subheader("Why use one?")
        st.write(
            "It gives AI agents and users a safe, separate place to try code, test ideas, and work with files without "
            "affecting the main application."
        )
        st.markdown(
            """**Common uses:**

- Run AI-generated code safely.
- Test commands and scripts before production.
- Give each user or session its own workspace.
- Build coding playgrounds and quick previews.
- Support multi-step agent workflows that create files and run commands.
"""
        )
        with st.expander("See how the agent, sandbox, and external services work together"):
            st.caption("The application stays in control: it decides what the agent can ask the sandbox to do and which results to keep.")
            st.graphviz_chart(
                """
                digraph sandbox_flow {
                    graph [rankdir=LR, bgcolor="transparent", pad="0.25", nodesep="0.45", ranksep="0.65"];
                    node [shape=box, style="rounded,filled", fontname="Arial", fontsize=12, margin="0.18,0.12"];
                    edge [fontname="Arial", fontsize=10, color="#7B8794", arrowsize=0.7];

                    user [label="User", fillcolor="#EAF2FF", color="#2F6FED"];
                    app [label="Your application\nor AI agent", fillcolor="#E8F8F0", color="#159957"];
                    sandbox [label="OCI GenAI Sandbox\nIsolated Linux workspace\n• run commands\n• create files", fillcolor="#FFF5E6", color="#E38B12"];
                    external [label="Approved external services\nModels, APIs, or web access", fillcolor="#F4EEFF", color="#7651C8"];
                    result [label="Selected results\nand files", fillcolor="#F6F8FA", color="#6E7781"];

                    user -> app [label="request"];
                    app -> sandbox [label="approved task"];
                    sandbox -> external [label="controlled access"];
                    external -> sandbox [label="response"];
                    sandbox -> app [label="output / artifacts"];
                    app -> result [label="validate and return"];
                }
                """
            )
            st.caption("The sandbox is temporary and separate from the main application. Only the outputs your application chooses to retrieve leave the workspace.")

        st.subheader("Sandbox vs. container vs. interpreter")
        st.write("These terms are related, but they describe different things:")
        st.table(
            [
                {
                    "Term": "OCI GenAI Sandbox",
                    "What it is": "A managed, temporary execution environment with its own workspace, session lifecycle, and controls.",
                    "Think of it as": "A safe, short-lived place for a task to run.",
                },
                {
                    "Term": "Container",
                    "What it is": "A packaged runtime image containing software and dependencies.",
                    "Think of it as": "The prepared toolset that can be used for a workload. A sandbox can use a standard runtime or an approved custom image.",
                },
                {
                    "Term": "Interpreter",
                    "What it is": "A program that runs a language, such as Python, Node.js, or Bash commands.",
                    "Think of it as": "One tool inside the workspace—not the workspace itself.",
                },
            ]
        )
        st.caption("In short: an interpreter runs code; a container packages software; a sandbox provides the isolated place where approved work happens.")
        st.info("This app is a tutorial companion. Runnable tutorials create short-lived sandboxes and request cleanup when they finish.")

    with tutorial:
        st.subheader("OCI GenAI Sandbox tutorials")
        st.caption("Each tutorial exposes the command sequence before anything is provisioned.")
        tutorials = {
            "Single-turn command": {
                "tag": "5 MIN · FIRST RUN",
                "labels": ["sandbox", "command", "beginner"],
                "summary": "Create a disposable sandbox, run one shell command, read stdout, then stop it.",
                "read_more": {
                    "workflow": [
                        "This is the smallest useful sandbox transaction: the application asks OCI for a short-lived runtime, waits until it is ready, submits one bounded command, and displays the returned output. It is a good first check that the project, region, and IAM policy are wired correctly before introducing packages, files, or agent orchestration.",
                        "Treat the command result as an observation, not durable application state. If a later step needs the result, collect it into the application or an approved artifact store before teardown; a stopped sandbox should not be used as a record system.",
                    ],
                    "flow": ["Create isolated runtime", "Wait for RUNNING", "Execute one allowlisted command", "Read stdout and exit status", "Stop runtime"],
                    "security": "Keep the command narrowly scoped and avoid putting secrets in command arguments, output, or filenames. Use a dedicated project with least-privilege IAM, set a short expiration, and always stop the sandbox in a finally/cleanup path when an error occurs.",
                },
                "trace": [
                    "Create — client.create_sandbox(project_id, CreateSandboxDetails(...))",
                    "Ready — client.get_sandbox(sandbox_id) → RUNNING",
                    "Execute — client.run_sandbox_command_and_wait(sandbox_id, command='pwd && ls -la')",
                    "Clean up — client.stop_sandbox(sandbox_id, StopSandboxDetails(is_force=False))",
                ],
                "code": """created = client.create_sandbox(project_id, CreateSandboxDetails(\n    display_name=\"single-turn-demo\", runtime=\"python-3.11\",\n    shape=\"SMALL\", expiration_duration=\"PT10M\",\n)).data\nwait_until_running(client, created.id)\nresult = client.run_sandbox_command_and_wait(\n    created.id, RunSandboxCommandDetails(command=\"pwd && ls -la\", timeout=\"PT2M\")\n).data\nprint(result.output.stdout)\nclient.stop_sandbox(created.id, StopSandboxDetails(is_force=False))""",
                "language": "python",
            },
            "Multi-turn workspace": {
                "tag": "10 MIN · STICKY SESSION",
                "labels": ["sandbox", "session", "workspace"],
                "summary": "Keep one sandbox ID across turns so files from the first command remain available to the next.",
                "read_more": {
                    "workflow": [
                        "A multi-turn workflow preserves one sandbox ID while the user completes related steps. The first turn writes a draft to `/workspace`; the second turn reads it back. That continuity is useful for iterative analysis, but it also means the application must deliberately own the session lifecycle rather than creating a new runtime for every button click.",
                        "Persist only the opaque sandbox identifier in server-side session state and associate it with the authenticated user and request. Make the next turn explicit, display the prior command history, and end the session when the task finishes or an inactivity deadline is reached.",
                    ],
                    "flow": ["Create once", "Store sandbox ID with session", "Write workspace state", "Run ordered follow-up turn", "Collect output", "Stop on completion or timeout"],
                    "security": "Never share a sandbox ID across users or browser sessions. Restrict commands to the expected workspace, validate any filenames supplied by a user, and do not treat files left in `/workspace` as trusted input on a later turn.",
                },
                "trace": [
                    "Create once — client.create_sandbox(...) → sandbox_id",
                    "Turn 1 — run_and_wait(command=\"echo draft > /workspace/brief.txt\")",
                    "Turn 2 — run_and_wait(command=\"cat /workspace/brief.txt\")",
                    "End session — client.stop_sandbox(sandbox_id, ...)",
                ],
                "code": """# Persist sandbox_id with the user session.\nclient.run_sandbox_command_and_wait(\n    sandbox_id,\n    RunSandboxCommandDetails(command=\"echo 'draft plan' > /workspace/brief.txt\", timeout=\"PT2M\"),\n)\nnext_turn = client.run_sandbox_command_and_wait(\n    sandbox_id, RunSandboxCommandDetails(command=\"cat /workspace/brief.txt\", timeout=\"PT2M\")\n).data\nprint(next_turn.output.stdout)""",
                "language": "python",
            },
            "Agent + OCI sandbox": {
                "tag": "20 MIN · AGENTS API",
                "labels": ["openai-agent", "sandbox", "executor"],
                "summary": "Connect a self-hosted Agents API session to OCI compute; the executor runs agent commands inside the sandbox.",
                "read_more": {
                    "workflow": [
                        "The application creates two separate concerns: an Agents API session that coordinates the work, and an OCI sandbox that executes tool commands. The executor bridges them, streaming agent events while keeping command execution inside the isolated runtime and returning only the files or results the application chooses to retrieve.",
                        "This pattern is appropriate when an agent needs a real workspace and repeatable tool environment. Keep the orchestrator responsible for approvals, artifact selection, and teardown; the sandbox is an execution boundary, not an authority to access every connected system.",
                    ],
                    "flow": ["Create agent session", "Provision OCI sandbox", "Start executor", "Stream agent/tool events", "Retrieve selected artifacts", "Delete session and stop sandbox"],
                    "security": "Use a dedicated executor credential with the minimum scope and short lifetime; do not copy the primary model key into the sandbox. Gate destructive or network-sensitive tools in the application, pin dependencies, and redact event logs before retaining them.",
                },
                "trace": [
                    "Session — create a self-hosted Agents API session with /workspace",
                    "Sandbox — create OCI sandbox and wait for RUNNING",
                    "Executor — install Codex and start codex exec-server",
                    "Agent turn — stream session events and retrieve artifacts from /workspace",
                    "Clean up — stop/delete sandbox, then delete the Agents API session",
                ],
                "code": """npm install -g @openai/codex\ncodex exec-server --environment-id \"$ENVIRONMENT_ID\" \\\n+  --environment-key \"$OPENAI_EXECUTOR_API_KEY\"\n\n# Keep OPENAI_API_KEY in the application. Pass only the executor\n# key into the sandbox as CODEX_API_KEY.""",
                "language": "bash",
            },
            "BYOC sandbox image": {
                "tag": "30 MIN · LIMITED AVAILABILITY",
                "labels": ["custom", "byoc", "container"],
                "summary": "Run a sandbox from a vetted custom image when the standard Python runtime does not include your required tools or dependencies.",
                "read_more": {
                    "workflow": [
                        "Bring-your-own-container starts before sandbox creation: build a minimal image, scan it, record its immutable digest, and publish it to an approved registry location. Provision the sandbox from that reviewed image, then run a small smoke command to prove that the expected runtime is present.",
                        "Use BYOC only when the managed image cannot satisfy a documented dependency. Keeping the Dockerfile and image provenance alongside the application gives reviewers a clear route from source, through build, to the exact image used by a session.",
                    ],
                    "flow": ["Build minimal image", "Scan and approve digest", "Publish to OCIR", "Provision by digest", "Run smoke check", "Record provenance and stop"],
                    "security": "Pin base images and package versions, run as a non-root user where supported, and exclude credentials, SSH keys, and build caches from image layers. Prefer an immutable image digest over a mutable tag and limit registry pull permissions to the sandbox project.",
                },
                "trace": [
                    "Build — create and scan a minimal image with only required tools",
                    "Publish — push the approved image to your OCI Container Registry path",
                    "Provision — create the sandbox with the BYOC image configuration",
                    "Verify — run a version check and a least-privilege smoke command",
                    "Clean up — stop the sandbox and retain image provenance outside the session",
                ],
                "code": """# Build and publish an approved, minimal image.\ndocker build -t <region>.ocir.io/<tenancy>/<repo>/sandbox-tools:1.0 .\ndocker push <region>.ocir.io/<tenancy>/<repo>/sandbox-tools:1.0\n\n# BYOC is limited-availability. Use the Oracle-provided beta SDK schema\n# for the image reference supplied to CreateSandboxDetails, then create\n# the sandbox and run an explicit smoke command such as: python --version.""",
                "language": "bash",
            },
            "Package + model artifact": {
                "tag": "15 MIN · ARTIFACT RETURN",
                "labels": ["python", "artifact", "model"],
                "summary": "Install a Python dependency, call an OCI-hosted model from the isolated workspace, then return a generated artifact to the application.",
                "read_more": {
                    "workflow": [
                        "This sample separates transient compute from the returned deliverable. The sandbox installs an approved dependency, runs a focused program, writes a structured `result.json`, and the application retrieves and validates that artifact before presenting a summary. The file format makes the boundary between sandbox work and application work explicit.",
                        "For production use, replace ad-hoc package installation with a locked dependency set or a vetted image, and define an artifact schema with size limits and validation. The application should reject malformed output rather than forwarding it directly into a later model prompt.",
                    ],
                    "flow": ["Start sandbox", "Prepare approved dependency", "Call approved model", "Write JSON artifact", "Validate and retrieve artifact", "Stop sandbox"],
                    "security": "Fetch credentials at runtime through Vault, Resource Principal, or another approved identity mechanism—never embed them in source, images, or output. Scope the model/project permission tightly, scrub artifacts for secrets, and validate JSON before a downstream model or user consumes it.",
                },
                "trace": [
                    "Create — start one sandbox for the application request",
                    "Prepare — install the approved Python package inside /workspace",
                    "Run — execute the program and write /workspace/result.json",
                    "Return — read the result file through the sandbox file/command API",
                    "Clean up — stop the sandbox after the artifact is collected",
                ],
                "code": """# The app injects OCI credentials from Vault or Resource Principal; never embed a key.\npython -m pip install --quiet pydantic\npython - <<'PY'\nimport json\nfrom openai import OpenAI\n\nclient = OpenAI(\n    base_url=\"https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1\",\n    api_key=runtime_oci_api_key(),  # retrieve at runtime, not from source\n    project=\"<sandbox-enabled-project-ocid>\",\n)\nresponse = client.responses.create(model=\"<approved-oci-model>\", input=\"Summarize this job.\")\nopen(\"/workspace/result.json\", \"w\").write(json.dumps({\"result\": response.output_text}))\nPY\ncat /workspace/result.json  # returned to the application as the job artifact""",
                "language": "bash",
            },
            "LangGraph research worker": {
                "tag": "10 MIN · LIVE AGENT WORKFLOW",
                "labels": ["langgraph", "multi-agent", "sandbox"],
                "summary": "Run a stateful LangGraph worker in a dedicated sandbox, persist intermediate research files, and return a structured report.",
                "read_more": {
                    "workflow": [
                        "The graph turns one research task into explicit nodes: research gathers bounded evidence, synthesis drafts a report, and review checks the output. Each node can write an intermediate file under `/workspace`, which makes debugging and artifact collection possible without confusing graph state with the final report.",
                        "Use a stable graph schema and checkpoint only the state that is needed to resume an approved follow-up. A caller should receive the final report plus selected diagnostics, not unrestricted access to every intermediate prompt, tool response, or workspace file.",
                    ],
                    "flow": ["Install locked graph dependencies", "Route task through research node", "Persist evidence", "Synthesize", "Review and serialize report", "Retrieve approved outputs"],
                    "security": "Constrain tools and node inputs separately: a model instruction is not an access-control policy. Keep credentials outside graph state, cap recursion/time/token budgets, validate retrieved content, and apply egress rules if a node can reach external sources.",
                },
                "trace": [
                    "Prepare — install langgraph and the approved tool dependencies",
                    "Plan — graph routes a question through research, synthesis, and review nodes",
                    "Execute — each node writes evidence and intermediate state under /workspace",
                    "Return — application retrieves report.json and node-level execution logs",
                    "Resume — reconnect to the same sandbox ID for an approved follow-up turn",
                ],
                "code": """python -m pip install langgraph openai\n# Research node: configured OCI artifact model.\n# Editor node: openai.gpt-oss-20b.\n# Define a StateGraph with research → editor nodes.\n# Invoke the graph and return the resulting report to the application.\n# Keep credentials in Vault/Resource Principal—not graph source or prompts.""",
                "language": "bash",
            },
            "Hybrid web research relay": {
                "tag": "15 MIN · MULTI-AGENT HANDOFF",
                "labels": ["openai-agent", "multi-agent", "web-search", "local-agent", "sandbox"],
                "summary": "A local planner delegates public-web research to a sandbox worker, then a separate local reviewer turns the returned evidence into a concise answer.",
                "read_more": {
                    "workflow": [
                        "The relay uses three deliberately separated roles. A local planner converts the request into a narrow query, the sandbox worker collects public evidence and emits a structured memo, and an independent local reviewer writes the final answer from that memo only. This separation keeps web retrieval, synthesis, and final presentation observable and testable.",
                        "The handoff is the key control point: parse and validate the memo, preserve source attribution, and label unavailable evidence rather than filling gaps with assumptions. The reviewer should see the validated evidence payload, not arbitrary shell output or the sandbox environment.",
                    ],
                    "flow": ["Plan constrained query locally", "Run sandbox web worker", "Write cited memo", "Validate memo schema", "Review only passed evidence", "Stop bounded worker"],
                    "security": "Apply an egress allowlist, request timeout, response-size cap, and a clear User-Agent for web retrieval. Treat retrieved pages as untrusted data: defend against prompt injection, do not expose internal URLs or credentials, and retain only approved citations and excerpts.",
                },
                "trace": [
                    "Local session A — planner produces a constrained public-web query",
                    "Sandbox session B — worker retrieves public evidence and writes a research memo",
                    "Handoff — application validates the JSON memo returned from the sandbox",
                    "Local session C — reviewer synthesizes only the passed evidence",
                    "Teardown — stop the sandbox after the one bounded research task",
                ],
                "code": """# Local planner session
query = local_model("Create a narrow public-web research query")

# OCI sandbox worker session: urllib retrieves public evidence; OCI model writes memo.
python -m pip install --quiet openai
python sandbox_web_worker.py --query "$QUERY" > memo.json

# Independent local reviewer session receives only memo.json.
answer = local_model(f"Synthesize this validated evidence: {memo_json}")""",
                "language": "python",
            },
            "CSV policy audit": {
                "tag": "8 MIN · DATA CHECK",
                "labels": ["python", "data", "policy", "sandbox"],
                "summary": "Create a small resource inventory in the sandbox, validate ownership fields, and return a machine-readable audit result.",
                "read_more": {
                    "workflow": [
                        "The sandbox receives or constructs a narrowly scoped inventory, then applies a deterministic policy check to it. The example identifies rows without an owner and returns a small JSON result; in a real audit, the same pattern can produce findings with rule identifiers, affected records, and remediation guidance.",
                        "Keep the audit logic deterministic and versioned so a result can be reproduced. The application should validate headers and row types before execution, then retain the policy version and input digest with the returned finding instead of keeping raw sensitive data longer than necessary.",
                    ],
                    "flow": ["Create disposable workspace", "Validate CSV schema", "Run versioned policy", "Emit JSON findings", "Validate result", "Stop sandbox"],
                    "security": "Classify the CSV before it enters the sandbox and minimize the columns provided. Reject spreadsheet formulas or unsafe encodings where relevant, prevent path traversal in uploaded filenames, and ensure returned findings do not disclose data beyond the user’s authorization.",
                },
                "trace": [
                    "Create — provision one disposable sandbox workspace",
                    "Write — create a sample inventory under /workspace",
                    "Audit — run a Python policy check against the file",
                    "Return — stream the JSON audit result to the application",
                    "Clean up — stop the short-lived sandbox",
                ],
                "code": '''printf 'name,owner\\nmodel-api,platform\\nreport-job,\\n' > /workspace/inventory.csv
python -c "import csv, json; rows=list(csv.DictReader(open('/workspace/inventory.csv'))); print(json.dumps({'missing_owner':[r['name'] for r in rows if not r['owner']]}))"''',
                "language": "bash",
            },
            "Release test gate": {
                "tag": "8 MIN · BUILD VALIDATION",
                "labels": ["python", "testing", "release", "sandbox"],
                "summary": "Build a tiny isolated application artifact, execute its test gate, and return the command result before release approval.",
                "read_more": {
                    "workflow": [
                        "A release gate creates a clean runtime, writes or retrieves the candidate artifact, and runs an explicit assertion suite. The application collects stdout, stderr, exit status, and a build identifier so a human or deployment workflow can make a decision using evidence from an isolated environment.",
                        "The sample is intentionally small, but its control flow scales to a real test command. Pin the source revision and dependencies, set a timeout, and define which test result is sufficient for approval; a passing command alone should not silently bypass required review or deployment controls.",
                    ],
                    "flow": ["Create clean runtime", "Materialize pinned artifact", "Run test gate", "Collect logs and status", "Publish decision evidence", "Stop sandbox"],
                    "security": "Do not give test code production credentials, deployment permissions, or unrestricted network access. Treat build inputs as untrusted, restrict writable paths, cap execution resources, and preserve logs according to retention policy without leaking tokens or configuration values.",
                },
                "trace": [
                    "Create — start a clean sandbox for the release check",
                    "Write — generate a small application module in /workspace",
                    "Test — run the isolated assertion gate",
                    "Return — collect stdout and exit status for approval",
                    "Clean up — stop the sandbox after validation",
                ],
                "code": '''printf 'def add(left, right): return left + right\\n' > /workspace/calculator.py
python -c "from pathlib import Path; exec(Path('/workspace/calculator.py').read_text()); assert add(2, 3) == 5; print('release gate passed')"''',
                "language": "bash",
            },
            "Structured document extraction": {
                "tag": "12 MIN · JSON CONTRACT",
                "labels": ["python", "document", "structured-output", "sandbox"],
                "summary": "Extract a small set of approved fields from a document, validate the result against a JSON contract, and return only the normalized record.",
                "read_more": {
                    "workflow": [
                        "This pattern puts a strict contract between unstructured input and downstream automation. The sandbox receives a bounded document, extracts only the requested fields, and serializes a small JSON record. The application validates that record before it is used by a database, workflow, or reviewer.",
                        "Keep extraction and acceptance separate: a model may propose values, while deterministic validation checks types, required fields, enumerations, and confidence thresholds. Route exceptions to a review queue instead of silently filling missing values or accepting extra fields.",
                    ],
                    "flow": ["Stage approved document", "Extract requested fields", "Write candidate JSON", "Validate schema and rules", "Return normalized record or review reason", "Stop sandbox"],
                    "security": "Minimize document access, encrypt sensitive source material at rest, and use a short retention period for workspace files. Never allow document text to redefine the extraction policy, and redact personal or confidential fields from logs and troubleshooting output.",
                },
                "trace": [
                    "Stage — copy one approved input document into /workspace",
                    "Extract — run the focused extraction program with an explicit field list",
                    "Validate — check result.json against the application JSON schema",
                    "Review — return a labelled exception when fields are missing or ambiguous",
                    "Clean up — collect the normalized record and stop the sandbox",
                ],
                "code": '''python extract.py --input /workspace/source.txt --fields invoice_id,amount,currency > /workspace/candidate.json
python -c "import json; from pathlib import Path; record=json.loads(Path('/workspace/candidate.json').read_text()); assert set(record) <= {'invoice_id','amount','currency'}; assert record['currency'] in {'USD','EUR','INR'}; print(json.dumps(record))"''',
                "language": "bash",
            },
            "Dependency SBOM check": {
                "tag": "12 MIN · SUPPLY CHAIN",
                "labels": ["python", "security", "dependencies", "sbom"],
                "summary": "Inspect a pinned dependency set in an isolated workspace, produce a compact SBOM, and flag packages outside the approved policy.",
                "read_more": {
                    "workflow": [
                        "A dependency check begins with a pinned requirements file or lockfile, not a mutable development environment. The sandbox installs or inspects that exact set, records package names and versions into a software bill of materials, and compares the result with the organization’s approved dependency policy.",
                        "Return the SBOM and policy findings as distinct artifacts. That lets a release process distinguish an informational inventory from a blocking exception and makes it possible to reproduce the check against the same source revision later.",
                    ],
                    "flow": ["Stage lockfile", "Resolve or inspect pinned packages", "Generate SBOM", "Compare with approval policy", "Return findings and digest", "Stop sandbox"],
                    "security": "Use an internal or allowlisted package index, require hashes where possible, and prohibit dependency resolution from arbitrary URLs. Do not execute package install hooks with elevated permissions, and make network access and cache contents part of the build evidence.",
                },
                "trace": [
                    "Stage — provide a lockfile and approved-package policy to /workspace",
                    "Inspect — enumerate exact package names and versions",
                    "Inventory — write sbom.json with a source and policy digest",
                    "Evaluate — flag unapproved, unpinned, or disallowed packages",
                    "Clean up — return findings without retaining the package cache",
                ],
                "code": '''python -m pip install --dry-run --requirement /workspace/requirements.txt
python -c "import importlib.metadata as m, json; components=sorted((d.metadata['Name'], d.version) for d in m.distributions() if d.metadata['Name']); print(json.dumps({'components':[{'name':name,'version':version} for name,version in components]}))" > /workspace/sbom.json''',
                "language": "bash",
            },
            "API contract smoke test": {
                "tag": "10 MIN · INTEGRATION CHECK",
                "labels": ["python", "api", "testing", "contract"],
                "summary": "Call an approved non-production endpoint with a fixed request fixture, verify its response contract, and return concise test evidence.",
                "read_more": {
                    "workflow": [
                        "An API smoke test proves a narrow integration without turning the sandbox into a general network scanner. The workspace loads a fixed fixture, calls one allowlisted non-production endpoint, then checks the response status, headers, and JSON shape against a declared contract.",
                        "A useful result captures the endpoint alias, contract version, timestamps, status, and assertion outcome—not raw request bodies or secrets. Failures should be actionable: report the assertion that failed and preserve a sanitized response sample only when policy permits it.",
                    ],
                    "flow": ["Load fixed fixture", "Call allowlisted test endpoint", "Check status and headers", "Validate response schema", "Return sanitized evidence", "Stop sandbox"],
                    "security": "Use short-lived test credentials scoped to a non-production tenant, keep endpoint hostnames on an egress allowlist, and block methods that mutate data unless an explicit isolated test account is used. Redact authorization headers, tokens, and customer data from all returned logs.",
                },
                "trace": [
                    "Prepare — load an approved fixture and endpoint alias",
                    "Request — issue one timeout-bound HTTPS request to the test service",
                    "Assert — verify response code, required headers, and schema",
                    "Return — emit sanitized JSON evidence and the assertion status",
                    "Clean up — stop the sandbox and invalidate temporary credentials",
                ],
                "code": '''python - <<'PY'
import json, os, urllib.request
request = urllib.request.Request(os.environ['TEST_API_URL'], headers={'Accept': 'application/json'})
with urllib.request.urlopen(request, timeout=10) as response:
    body = json.load(response)
    assert response.status == 200 and 'id' in body
    print(json.dumps({'status': response.status, 'contract': 'passed'}))
PY''',
                "language": "bash",
            },
        }
        def render_flow_diagram(name: str, flow: list[str]) -> None:
            """Render a compact, sample-specific view of the sandbox handoff."""
            def dot_label(value: str) -> str:
                return value.replace("\\", "\\\\").replace('"', '\\"')

            steps = "\\n".join(f"{index}. {step}" for index, step in enumerate(flow, start=1))
            st.caption(f"{name}: your application controls the request, the sandbox performs the isolated work, and only selected results return.")
            st.graphviz_chart(
                f'''digraph tutorial_flow {{
                    graph [rankdir=LR, bgcolor="transparent", pad="0.25", nodesep="0.4", ranksep="0.6"];
                    node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11, margin="0.16,0.11"];
                    edge [fontname="Arial", fontsize=9, color="#7B8794", arrowsize=0.7];

                    caller [label="User or calling app", fillcolor="#EAF2FF", color="#2F6FED"];
                    app [label="Application / agent\\napproves the task", fillcolor="#E8F8F0", color="#159957"];
                    sandbox [label="OCI GenAI Sandbox\\nisolated workspace", fillcolor="#FFF5E6", color="#E38B12"];
                    work [label="{dot_label(steps)}", fillcolor="#F4EEFF", color="#7651C8"];
                    external [label="Approved input or services\\nwhen the sample needs them", fillcolor="#EAF2FF", color="#2F6FED"];
                    result [label="Validated result\\nor selected files", fillcolor="#F6F8FA", color="#6E7781"];

                    caller -> app [label="request"];
                    app -> sandbox [label="approved work"];
                    sandbox -> work [label="run sample"];
                    work -> sandbox [label="output"];
                    external -> sandbox [label="controlled access", style=dashed];
                    sandbox -> external [label="bounded request", style=dashed];
                    sandbox -> app [label="artifacts / status"];
                    app -> result [label="return"];
                }}'''
            )

        @st.dialog("Tutorial details", width="large")
        def show_read_more(name: str, details: dict) -> None:
            st.subheader(name)
            for paragraph in details["read_more"]["workflow"]:
                st.write(paragraph)
            st.markdown("#### Execution flow")
            st.markdown(" → ".join(details["read_more"]["flow"]))
            with st.expander("View the interaction diagram", expanded=False):
                render_flow_diagram(name, details["read_more"]["flow"])
            st.markdown("#### Security constraints")
            st.write(details["read_more"]["security"])
            if st.button("Close", key=f"close-read-more-{name}"):
                st.session_state.pop("read_more_tutorial", None)
                st.session_state.selected_tutorial = None
                st.rerun()

        runnable_tutorials = {
            "Single-turn command", "Multi-turn workspace", "Package + model artifact",
            "LangGraph research worker", "Hybrid web research relay", "CSV policy audit",
            "Release test gate", "Structured document extraction", "Dependency SBOM check",
            "API contract smoke test",
        }

        if "selected_tutorial" not in st.session_state:
            st.session_state.selected_tutorial = None
        requested_read_more = st.query_params.get("read_more")
        requested_tutorial = st.query_params.get("tutorial")
        if requested_read_more in tutorials:
            st.session_state.read_more_tutorial = requested_read_more
            st.query_params.clear()
        elif requested_tutorial in tutorials:
            st.session_state.selected_tutorial = requested_tutorial
            st.query_params.clear()
        if st.session_state.selected_tutorial is None:
            search_text = st.text_input(
                "Search tutorials or labels",
                placeholder="Try: openai-agent, langgraph, custom, workspace…",
            ).strip().lower()
            matching_tutorials = [
                (name, details)
                for name, details in tutorials.items()
                if not search_text or search_text in " ".join(
                    [name, details["summary"], details["tag"], *details["labels"]]
                ).lower()
            ]
            st.caption("Filter by title, description, or labels such as openai-agent, langgraph, custom, sandbox, and web-search.")
            if not matching_tutorials:
                st.info("No tutorials match that search. Try a broader label such as `sandbox` or `multi-agent`.")
            for row_start in range(0, len(matching_tutorials), 2):
                columns = st.columns(2, gap="large")
                for column, (name, details) in zip(columns, matching_tutorials[row_start:row_start + 2]):
                    with column:
                        labels = "".join(f'<span class="label-chip">{escape(label)}</span>' for label in details["labels"])
                        run_badge = '<span class="run-badge">Run enabled</span>' if name in runnable_tutorials else ''
                        st.markdown(
                            f'<div class="step-card"><div class="step-number">{details["tag"]}</div><h3>{name}</h3>'
                            f'{run_badge}<div>{labels}</div><p>{details["summary"]}</p></div>',
                            unsafe_allow_html=True,
                        )
                        read_more, open_tutorial = st.columns(2)
                        with read_more:
                            if st.button("Read more", key=f"read-more-{name}", use_container_width=True):
                                st.session_state.read_more_tutorial = name
                        with open_tutorial:
                            if st.button("Open tutorial", key=f"tutorial-{name}", use_container_width=True):
                                st.session_state.selected_tutorial = name
                                st.rerun()
            read_more_name = st.session_state.get("read_more_tutorial")
            if read_more_name:
                show_read_more(read_more_name, tutorials[read_more_name])
        else:
            if st.button("← All tutorials"):
                st.session_state.selected_tutorial = None
                st.rerun()
            selected_name = st.session_state.selected_tutorial
            selected = tutorials[selected_name]
            header_text, header_action = st.columns((4, 1))
            with header_text:
                labels = "".join(f'<span class="label-chip">{escape(label)}</span>' for label in selected["labels"])
                st.markdown(f'<div class="tutorial-heading"><div class="step-number">{selected["tag"]}</div><h2>{selected_name}</h2><div>{labels}</div><p>{selected["summary"]}</p></div>', unsafe_allow_html=True)
            with header_action:
                should_run = st.session_state.pop("run_tutorial_now", None) == selected_name
                if selected_name in runnable_tutorials:
                    should_run = st.button("Run tutorial", type="primary", use_container_width=True) or should_run
            session_column, execution_column = st.columns((1, 1.25), gap="large")
            with session_column:
                with st.expander("Read more: workflow & safeguards", expanded=False):
                    for paragraph in selected["read_more"]["workflow"]:
                        st.write(paragraph)
                    st.markdown("**Execution flow**")
                    st.markdown(" → ".join(selected["read_more"]["flow"]))
                    with st.expander("View the interaction diagram", expanded=False):
                        render_flow_diagram(selected_name, selected["read_more"]["flow"])
                    st.markdown("**Security constraints**")
                    st.write(selected["read_more"]["security"])
                with st.expander("Session lifecycle", expanded=False):
                    for index, item in enumerate(selected["trace"], start=1):
                        st.markdown(f"`{index}` {item}")
                with st.expander("Session boundary", expanded=False):
                    st.write("One sandbox ID maps to one isolated workspace. Keep that ID for follow-up turns; stop it when the user session ends.")
                if selected_name == "Multi-turn workspace":
                    with st.expander("What this covers", expanded=False):
                        st.write("Sticky sandbox ID, durable `/workspace` state, ordered command turns, stdout collection, and explicit session teardown. It does not yet cover snapshots, forks, file-upload APIs, or concurrent users.")
            with execution_column:
                with st.expander("Actual code", expanded=False):
                    st.code(selected["code"], language=selected["language"])
                if selected_name == "Agent + OCI sandbox":
                    st.warning("Live Agents API execution requires OPENAI_API_KEY and OPENAI_EXECUTOR_API_KEY plus the Oracle sandbox beta SDK. These are intentionally not present in this local configuration.")
                elif selected_name in runnable_tutorials:
                    st.caption("Run this tutorial to provision a short-lived OCI sandbox and stream the actual API events.")
                else:
                    st.info("This reference view shows the workflow and command shape without provisioning a sandbox.")
            st.warning("OCI GenAI Sandboxes are limited-availability. Use the Oracle-provided beta SDK and a sandbox-enabled project before provisioning.")
            if selected_name in runnable_tutorials:
                st.markdown("#### Live execution console")
                console_panel = st.empty()
                timeline_key = f"tutorial_timeline_{selected_name}"

                def render_console(entries: list[str]) -> None:
                    console_panel.markdown(console_markup(entries, "execution-console"), unsafe_allow_html=True)

                if should_run:
                    commands = None
                    if selected_name == "Multi-turn workspace":
                        commands = ["echo 'draft plan' > /workspace/brief.txt", "cat /workspace/brief.txt"]
                    elif selected_name == "CSV policy audit":
                        commands = [
                            "printf 'name,owner\\nmodel-api,platform\\nreport-job,\\n' > /workspace/inventory.csv",
                            "python -c \"import csv, json; rows=list(csv.DictReader(open('/workspace/inventory.csv'))); print(json.dumps({'missing_owner':[r['name'] for r in rows if not r['owner']]}))\"",
                        ]
                    elif selected_name == "Release test gate":
                        commands = ["printf 'def add(left, right): return left + right\\n' > /workspace/calculator.py", "python -c \"from pathlib import Path; exec(Path('/workspace/calculator.py').read_text()); assert add(2, 3) == 5; print('release gate passed')\""]
                    elif selected_name == "Structured document extraction":
                        commands = ["printf 'invoice_id=INV-1042\\namount=1250.00\\ncurrency=INR\\n' > /workspace/source.txt", "python -c \"import json; source=dict(line.strip().split('=', 1) for line in open('/workspace/source.txt') if line.strip()); result={'invoice_id': source['invoice_id'], 'amount': float(source['amount']), 'currency': source['currency']}; assert result['currency'] in {'USD', 'EUR', 'INR'}; print(json.dumps(result))\""]
                    elif selected_name == "Dependency SBOM check":
                        commands = ["printf 'python-dotenv==1.0.0\\nstreamlit==1.64.0\\n' > /workspace/requirements.txt", "python -c \"import json; packages=[line.strip().split('==', 1) for line in open('/workspace/requirements.txt') if line.strip()]; approved={'python-dotenv', 'streamlit'}; findings=[name for name, version in packages if name not in approved or not version]; print(json.dumps({'components': [{'name': name, 'version': version} for name, version in packages], 'unapproved': findings}))\""]
                    elif selected_name == "API contract smoke test":
                        commands = ["printf '{\\\"id\\\": \\\"demo-123\\\", \\\"status\\\": \\\"ready\\\"}\\n' > /workspace/api-response.json", "python -c \"import json; body=json.load(open('/workspace/api-response.json')); assert set(body) == {'id', 'status'} and body['status'] == 'ready'; print(json.dumps({'status': 200, 'contract': 'passed'}))\""]
                    timeline: list[str] = []
                    try:
                        sandbox_memo = None
                        artifact_payload = None
                        step_started = time.perf_counter()
                        if selected_name == "Hybrid web research relay":
                            events = run_hybrid_web_research(project_id, region, value("OCI_CLI_PROFILE", "DEFAULT"), api_key, artifact_model, compartment_id)
                        elif selected_name == "LangGraph research worker":
                            events = run_langgraph_research(project_id, region, value("OCI_CLI_PROFILE", "DEFAULT"), api_key, artifact_model)
                        elif selected_name == "Package + model artifact":
                            events = run_package_model_artifact(project_id, region, value("OCI_CLI_PROFILE", "DEFAULT"), api_key, artifact_model)
                        else:
                            events = run_single_turn(project_id, region, value("OCI_CLI_PROFILE", "DEFAULT"), commands)
                        for event in events:
                            elapsed = time.perf_counter() - step_started
                            if selected_name == "Hybrid web research relay" and "SANDBOX_MEMO=" in event:
                                sandbox_memo = event.split("SANDBOX_MEMO=", 1)[1].strip()
                            if selected_name == "Package + model artifact" and "ARTIFACT_JSON=" in event:
                                artifact_payload = event.split("ARTIFACT_JSON=", 1)[1].strip()
                            timeline.append(timed_event(event, elapsed))
                            render_console(timeline)
                            step_started = time.perf_counter()
                        if selected_name == "Package + model artifact" and artifact_payload:
                            handoff_started = time.perf_counter()
                            timeline.append(timed_event("Application handoff → validate result.json returned by the sandbox", 0))
                            artifact = json.loads(artifact_payload)
                            if not isinstance(artifact.get("model"), str) or not isinstance(artifact.get("result"), str):
                                raise ValueError("Sandbox artifact is missing the required model or result string.")
                            timeline.append(
                                timed_event(
                                    f"Application handoff ← validated result.json from model {artifact['model']}; result is ready for the caller",
                                    time.perf_counter() - handoff_started,
                                )
                            )
                        if selected_name == "Hybrid web research relay" and sandbox_memo:
                            handoff_started = time.perf_counter()
                            timeline.append(timed_event("Application handoff → validate sandbox memo JSON (query, evidence, memo)", 0))
                            memo_payload = json.loads(sandbox_memo)
                            if not isinstance(memo_payload.get("query"), str) or not isinstance(memo_payload.get("memo"), str):
                                raise ValueError("Sandbox memo is missing the required query or memo string.")
                            evidence = memo_payload.get("evidence")
                            if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
                                raise ValueError("Sandbox memo evidence must be a list of source records.")
                            timeline.append(
                                timed_event(
                                    f"Application handoff ← validated memo; passing {len(evidence)} evidence item(s) to local reviewer only",
                                    time.perf_counter() - handoff_started,
                                )
                            )
                            reviewer_started = time.perf_counter()
                            timeline.append("Local reviewer session C → synthesize only the validated sandbox memo\n⏱ Step time: 0.00s")
                            review = run_prompt(
                                OciOpenAIConfig(region, compartment_id, project_id, model, api_key),
                                "Write one concise answer based only on this validated sandbox research memo: " + memo_payload["memo"],
                            )
                            timeline.append(timed_event(f"Local reviewer output ← {review}", time.perf_counter() - reviewer_started))
                            render_console(timeline)
                    except Exception as exc:
                        timeline.append(timed_event(f"ERROR: {exc}", time.perf_counter() - step_started))
                    st.session_state[timeline_key] = timeline
                render_console(st.session_state.get(timeline_key, []))

    with validate:
        st.subheader("Validate OCI project access")
        st.write("This small request verifies the project credentials that you will use while following sandbox tutorials. It does not create a sandbox.")
        prompt = st.text_area(
            "Test prompt",
            value="Reply with: OCI sandbox project access verified.",
            height=104,
        )
        if st.button("Validate OCI access", type="primary"):
            missing = [
                label
                for label, current in (("Generative AI Project OCID", project_id), ("Generative AI API key", api_key))
                if not current
            ]
            if missing:
                st.error("Add " + " and ".join(missing) + " in the sidebar or .env file.")
            else:
                config = OciOpenAIConfig(region, compartment_id, project_id, model, api_key)
                try:
                    with st.spinner("Validating OCI project access…"):
                        output = run_prompt(config, prompt)
                    st.success("OCI project access validated.")
                    st.markdown(output)
                except Exception as exc:
                    st.error(f"OCI validation failed: {exc}")

    with resources:
        st.subheader("Your tutorial context")
        st.table(
            [
                {"Resource": "Compartment", "Value": compartment_id, "Why it matters": "Sandbox ownership boundary"},
                {"Resource": "Region", "Value": region, "Why it matters": "Feature and model availability"},
                {"Resource": "Generative AI Project", "Value": project_id or "Add during setup", "Why it matters": "Sandbox and model project context"},
                {"Resource": "API key", "Value": "Configured locally" if api_key else "Add during setup", "Why it matters": "Validates model access"},
            ],
            hide_index=True,
        )
        st.markdown("#### What this tutorial app does not do")
        st.write("It does not provision persistent infrastructure, store credentials, or remove resources. Each runnable lab creates only a short-lived sandbox and explicitly requests its stop when complete.")
        st.markdown("#### References")
        st.markdown(
            "- [OCI provider guide for OpenAI environments](https://developers.openai.com/api/docs/guides/agents-api/environments/providers/oci)\n"
            "- [OpenAI Agents SDK: orchestration patterns](https://openai.github.io/openai-agents-python/multi_agent/)\n"
        )

    st.markdown(
        f'<footer class="app-footer">Last deployed / app started: {APP_STARTED_AT_UTC}</footer>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
