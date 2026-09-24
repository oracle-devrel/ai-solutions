# OCI GenAI Sandbox Lab

An interactive Streamlit lab for OCI Generative AI Sandboxes and OCI's OpenAI-compatible Responses API. It combines executable sandbox tutorials, live API/command output, and concise reference material.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy python3 run.py
```

## Run with Docker

Build the image, then provide configuration only at runtime (the `.env` file is
excluded from the build context):

```bash
docker build -t oci-sandbox-lab .
docker run --rm --init -p 8501:8501 --env-file .env \
  --env HTTP_PROXY= --env HTTPS_PROXY= --env ALL_PROXY= \
  --env http_proxy= --env https_proxy= --env all_proxy= \
  --env NO_PROXY='*' --env no_proxy='*' oci-sandbox-lab
```

Open <http://localhost:8501>. Set `APP_PASSWORD` in `.env` before starting a
container; otherwise the generated password is printed in the container logs.
The OCI Sandbox tutorial actions additionally require Oracle's preview OCI SDK
and an OCI user-principal configuration. Mount these at runtime only if those
actions are needed; model-only features work with the dependencies in
`requirements.txt`.

The app opens with a login screen. The username is `oci` unless `APP_USER` is set.
Set `APP_PASSWORD` to choose the password; if it is absent, the app creates a secure
16-character alphanumeric password before Streamlit starts and prints it to the
terminal. The generated password remains valid for that app process.

Set these values in `.env`:

```dotenv
OCI_REGION=us-chicago-1
OCI_SANDBOX_PROJECT_ID=ocid1.generativeaiproject.oc1.us-chicago-1...
OCI_GENAI_PROJECT_ID=ocid1.generativeaiproject.oc1.us-chicago-1...
OCI_GENAI_API_KEY=your-oci-generative-ai-api-key-secret
OCI_MODEL_ID=openai.gpt-oss-120b
OCI_ARTIFACT_MODEL_ID=openai.gpt-oss-120b
APP_USER=oci
APP_PASSWORD=choose-a-strong-password
```

`OCI_SANDBOX_PROJECT_ID` must refer to a project with GenAI Sandbox enabled. The app disables proxy inheritance for OCI Sandbox SDK and OCI OpenAI-compatible model calls.

## Tutorial catalog

Use **Search tutorials or labels** to filter by title, description, or labels such as `openai-agent`, `langgraph`, `custom`, `sandbox`, and `web-search`.

| Tutorial | Labels | Live execution |
| --- | --- | --- |
| Single-turn command | `sandbox`, `command`, `beginner` | Yes |
| Multi-turn workspace | `sandbox`, `session`, `workspace` | Yes |
| Agent + OCI sandbox | `openai-agent`, `sandbox`, `executor` | Prerequisites shown |
| BYOC sandbox image | `custom`, `byoc`, `container` | Reference workflow |
| Package + model artifact | `python`, `artifact`, `model` | Yes |
| LangGraph research worker | `langgraph`, `multi-agent`, `sandbox` | Yes |
| Hybrid web research relay | `openai-agent`, `multi-agent`, `web-search`, `local-agent` | Yes |
| CSV policy audit | `python`, `data`, `policy` | Yes |
| Release test gate | `python`, `testing`, `release` | Yes |
| Structured document extraction | `python`, `document`, `structured-output` | Yes |
| Dependency SBOM check | `python`, `security`, `dependencies`, `sbom` | Yes |
| API contract smoke test | `python`, `api`, `testing`, `contract` | Yes |

## Using the tutorial catalog

The **Sandbox tutorial** tab is the default landing view. Each sample tile offers **Read more** for a closable workflow, execution-flow, and security-constraints overview, plus **Open tutorial** for the complete lifecycle and code reference. Closing the Read more dialog returns to the tutorial catalog.

Runnable samples display a **Run enabled** badge. Open one of those samples to use its **Run tutorial** control and watch the chronological live execution console. The catalog intentionally does not provision sandboxes directly.

## Live execution console

Runnable tutorials stream the actual OCI SDK lifecycle and command results into one chronological console:

- `▶ Command` — command submitted to the sandbox.
- `↳ Output` — stdout, stderr, and command exit result.
- `● Activity` — provisioning, polling, and local-agent handoffs.
- `⚠ Error` — a failed command or API call.

The console auto-follows new events, has a fixed-height scrollbar, and includes **Copy console**. For credential-bearing launches, only the opaque `exec(base64...)` payload is omitted; the visible command shape and decoded Python source remain available. API keys are never displayed.

## Hybrid web research relay

The runnable relay uses three bounded sessions: local OCI-model planner → OCI sandbox web worker → separate local OCI-model reviewer. The worker identifies itself to Wikipedia with a User-Agent. If a source or sandbox egress policy denies public access, it returns a labelled unavailable-evidence item and completes the handoff transparently rather than inventing sources.

The lab uses deterministic application orchestration because it operates with OCI credentials and OCI's OpenAI-compatible endpoint. The architecture maps to the OpenAI Agents SDK code-orchestrated multi-agent pattern.

## Infrastructure and security

See [infra/README.md](infra/README.md) for project creation, sandbox enablement, IAM, and preview SDK bootstrap. Never commit `.env`, API keys, or raw credential-bearing commands.

## References

- [OCI provider guide for OpenAI environments](https://developers.openai.com/api/docs/guides/agents-api/environments/providers/oci)
- [OpenAI Agents SDK: agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/)
