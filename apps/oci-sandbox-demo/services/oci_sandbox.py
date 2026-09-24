"""Live OCI GenAI Sandbox tutorial operations (requires Oracle's beta OCI SDK)."""

from __future__ import annotations

import time
import base64
import os
import shlex
from collections.abc import Iterator


def _display_program_command(project_id: str, launcher: str, script: str) -> str:
    """Return the visible executable portion of a sandbox program launch."""
    # Keep the command shape readable while omitting only the opaque payload.
    # The decoded program is shown directly below it for review and copying.
    visible_launcher = 'python -c "import base64; [exec(base64.b64decode(...)) omitted]"'
    return (
        "OCI SDK → run_sandbox_command_and_wait:\n"
        "# OCI runtime environment prepared for this execution.\n"
        f"OCI_GENAI_PROJECT_ID={shlex.quote(project_id)} {visible_launcher}\n"
        "# Decoded Python program executed by the launcher:\n"
        f"{script}"
    )


def run_single_turn(
    project_id: str, region: str, profile: str = "DEFAULT", commands: list[str] | None = None
) -> Iterator[str]:
    """Create, exercise, and stop a sandbox while yielding truthful live API events."""
    try:
        import oci
        from oci.generative_ai_sandbox import GenerativeAiSandboxClient
        from oci.generative_ai_sandbox.models import (
            CreateSandboxDetails,
            RunSandboxCommandDetails,
            StopSandboxDetails,
        )
    except ImportError as exc:
        raise RuntimeError(
            "The Oracle sandbox beta SDK is not installed. Set OCI_SANDBOX_SDK_WHEEL to the "
            "Oracle-provided wheel and run infra/bootstrap_sandbox_project.sh --apply."
        ) from exc

    endpoint = f"https://inference.generativeai.{region}.oci.oraclecloud.com"
    # OCI Container Instances exposes resource-principal v2.2 variables when
    # resource-principal access is enabled.  Prefer those workload credentials:
    # they require no ~/.oci/config or user API signing key in the image.
    if os.getenv("OCI_RESOURCE_PRINCIPAL_VERSION"):
        signer = oci.auth.signers.get_resource_principals_signer()
        client = GenerativeAiSandboxClient(
            config={"region": region}, signer=signer, service_endpoint=endpoint
        )
    else:
        # Local development continues to use the named user-principal profile.
        config = oci.config.from_file(profile_name=profile)
        client = GenerativeAiSandboxClient(config=config, service_endpoint=endpoint)
    # OCI's vendored Requests session otherwise inherits HTTP(S)_PROXY from the
    # Streamlit process. Sandbox API traffic must connect directly in this lab.
    client.base_client.session.trust_env = False
    client.base_client.session.proxies = {}
    yield f"OCI SDK → POST sandbox (project={project_id})"
    created = client.create_sandbox(
        project_id,
        CreateSandboxDetails(
            display_name="sandbox-lab-single-turn",
            runtime="python-3.11",
            shape="SMALL",
            expiration_duration="PT10M",
        ),
    ).data
    sandbox_id = created.id
    yield f"OCI API ← sandbox created: {sandbox_id}"

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        sandbox = client.get_sandbox(sandbox_id).data
        yield f"OCI SDK → GET sandbox/{sandbox_id}  state={sandbox.lifecycle_state}"
        if sandbox.lifecycle_state == "RUNNING":
            break
        if sandbox.lifecycle_state in {"FAILED", "DELETED"}:
            raise RuntimeError(f"Sandbox entered {sandbox.lifecycle_state}.")
        time.sleep(2)
    else:
        raise TimeoutError("Sandbox did not reach RUNNING within two minutes.")

    commands = commands or ["pwd && printf '\\n-- workspace --\\n' && ls -la"]
    for command in commands:
        yield f"OCI SDK → run_sandbox_command_and_wait: {command}"
        result = client.run_sandbox_command_and_wait(
            sandbox_id, RunSandboxCommandDetails(command=command, timeout="PT2M")
        ).data
        output = result.output
        yield f"OCI API ← command exit={output.exit_code}\n{output.stdout or ''}{output.stderr or ''}"
    yield "OCI SDK → stop_sandbox"
    client.stop_sandbox(sandbox_id, StopSandboxDetails(is_force=False))
    yield "OCI API ← sandbox stop requested"


def run_package_model_artifact(
    project_id: str, region: str, profile: str, api_key: str, model: str
) -> Iterator[str]:
    """Run a dependency install and OCI model call inside a sandbox, returning its artifact."""
    script = f'''import json, os
from openai import OpenAI
client = OpenAI(
    base_url="https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
    api_key=os.environ["OCI_GENAI_API_KEY"],
    project=os.environ["OCI_GENAI_PROJECT_ID"],
)
response = client.responses.create(model={model!r}, input="Summarize why isolated sandboxes are useful in one sentence.")
with open("/workspace/result.json", "w") as artifact:
    json.dump({{"model": {model!r}, "result": response.output_text}}, artifact)
print("ARTIFACT_JSON=" + open("/workspace/result.json").read())'''
    encoded = base64.b64encode(script.encode()).decode()
    launcher = f"python -c \"import base64; exec(base64.b64decode('{encoded}'))\""
    command = f"OCI_GENAI_API_KEY={shlex.quote(api_key)} OCI_GENAI_PROJECT_ID={shlex.quote(project_id)} {launcher}"
    for event in run_single_turn(
        project_id,
        region,
        profile,
        ["python -m pip install --quiet openai", command],
    ):
        if event.startswith("OCI SDK → run_sandbox_command_and_wait:") and command in event:
            yield _display_program_command(project_id, launcher, script)
        else:
            yield event.replace(api_key, "[REDACTED]")


def run_langgraph_research(project_id: str, region: str, profile: str, api_key: str, model: str) -> Iterator[str]:
    """Run researcher and editor LangGraph nodes inside one OCI sandbox.

    Command section:
      1. Install ``langgraph`` and ``openai`` in the short-lived sandbox.
      2. Run this program using OCI runtime credentials supplied to the process.
      3. Route research through the configured artifact model and editing through
         ``openai.gpt-oss-20b``.
      4. Return the final graph report on stdout before sandbox teardown.
    """
    script = f'''"""OCI Sandbox LangGraph research workflow.

Command section
===============
Install command:
    python -m pip install --quiet langgraph openai

Program command:
    python -c "import base64; exec(base64.b64decode(...))"

Runtime behavior:
    * OCI runtime credentials are injected outside this source program.
    * ``research`` calls the configured artifact model: {model}.
    * ``editor`` calls openai.gpt-oss-20b to produce an executive summary.
    * The compiled StateGraph runs research → editor and prints the final report.
"""
import os
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from openai import OpenAI
client = OpenAI(base_url="https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1", api_key=os.environ["OCI_GENAI_API_KEY"], project=os.environ["OCI_GENAI_PROJECT_ID"])
class State(TypedDict):
    topic: str
    research: str
    report: str
def research(state):
    return {{"research": client.responses.create(model={model!r}, input="Research in one sentence: " + state["topic"]).output_text}}
def editor(state):
    return {{"report": client.responses.create(model="openai.gpt-oss-20b", input="Write an executive summary: " + state["research"]).output_text}}
graph = StateGraph(State)
graph.add_node("research", research); graph.add_node("editor", editor)
graph.add_edge(START, "research"); graph.add_edge("research", "editor"); graph.add_edge("editor", END)
print(graph.compile().invoke({{"topic": "OCI session-isolated sandboxes"}})["report"])'''
    encoded = base64.b64encode(script.encode()).decode()
    launcher = f"python -c \"import base64; exec(base64.b64decode('{encoded}'))\""
    command = f"OCI_GENAI_API_KEY={shlex.quote(api_key)} OCI_GENAI_PROJECT_ID={shlex.quote(project_id)} {launcher}"
    for event in run_single_turn(project_id, region, profile, ["python -m pip install --quiet langgraph openai", command]):
        if event.startswith("OCI SDK → run_sandbox_command_and_wait:") and command in event:
            yield _display_program_command(project_id, launcher, script)
        else:
            yield event.replace(api_key, "[REDACTED]")


def run_hybrid_web_research(
    project_id: str, region: str, profile: str, api_key: str, model: str, compartment_id: str
) -> Iterator[str]:
    """Run local planner → sandbox web worker → local reviewer handoff sessions."""
    from services.oci_openai import OciOpenAIConfig, run_prompt

    config = OciOpenAIConfig(region, compartment_id, project_id, model, api_key)
    yield "Local planner session A → create a narrow public-web research query"
    query = run_prompt(config, "Return only a 6-10 word web research query about OCI sandbox isolation.")
    yield f"Local planner output → {query}"
    script = f'''"""Sandbox web-research worker.

Command section:
    * Use Python standard-library urllib to query Wikipedia's public search API.
    * Give the retrieved titles and snippets to the OCI model for a cited memo.
    * Print SANDBOX_MEMO JSON for the local reviewer session.
"""
import json, os
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from openai import OpenAI

query = {query!r}
url = "https://en.wikipedia.org/w/api.php?" + urlencode({{
    "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 3,
}})
request = Request(url, headers={{
    "User-Agent": "OCI-Sandbox-Lab/1.0 (tutorial research worker)",
    "Accept": "application/json",
}})
try:
    with urlopen(request, timeout=20) as response:
        results = json.load(response)["query"]["search"]
    evidence = [{{"title": item["title"], "snippet": item["snippet"]}} for item in results]
except (HTTPError, URLError, TimeoutError) as exc:
    # Keep the local reviewer handoff real and explicit when a sandbox network
    # policy or a source service declines the request.
    evidence = [{{"title": "Public web retrieval unavailable", "snippet": f"{{type(exc).__name__}}: {{exc}}"}}]
client = OpenAI(
    base_url="https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
    api_key=os.environ["OCI_GENAI_API_KEY"], project=os.environ["OCI_GENAI_PROJECT_ID"],
)
memo = client.responses.create(
    model={model!r},
    input="Create a factual 3-bullet research memo from this public evidence. Include titles; do not invent sources. " + json.dumps(evidence),
).output_text
print("SANDBOX_MEMO=" + json.dumps({{"query": query, "evidence": evidence, "memo": memo}}))'''
    encoded = base64.b64encode(script.encode()).decode()
    launcher = f"python -c \"import base64; exec(base64.b64decode('{encoded}'))\""
    command = f"OCI_GENAI_API_KEY={shlex.quote(api_key)} OCI_GENAI_PROJECT_ID={shlex.quote(project_id)} {launcher}"
    yield "Sandbox worker session B → retrieve bounded public evidence and write SANDBOX_MEMO"
    for event in run_single_turn(project_id, region, profile, ["python -m pip install --quiet openai", command]):
        if event.startswith("OCI SDK → run_sandbox_command_and_wait:") and command in event:
            yield _display_program_command(project_id, launcher, script)
        else:
            yield event.replace(api_key, "[REDACTED]")
