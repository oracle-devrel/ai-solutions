# OCI Routing Profile Lab

A local app for exercising OCI Generative AI routing profiles through four SDK workflows. Each request uses the selected routing-profile OCID as the model identifier and records the response's `x-genai-selected-region` header.

| Experiment mode | Client | Authentication |
| --- | --- | --- |
| Direct inference | OpenAI Python SDK, Responses API | OCI Generative AI API key |
| LangChain agent | `ChatOpenAI`, Chat Completions API | OCI Generative AI API key |
| Agents SDK | OpenAI Agents SDK, Chat Completions API | OCI Generative AI API key |
| OCI Python SDK | Native OCI Chat API | OCI request signing with the configured OCI profile |

The API key stays on the server. Credential headers are redacted before appearing in the browser's completion logs.

## Setup and run

1. Create a routing profile with the [Terraform instructions](#terraform-infrastructure), or use an existing profile.
2. Configure OCI credentials in `~/.oci/config` for profile reads and native OCI SDK inference.
3. Copy `.env.example` to `.env`, replace the placeholders, install dependencies, and start the server:

```sh
cp .env.example .env
# Edit .env before starting the app.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open [http://localhost:3000](http://localhost:3000). To change the port:

```sh
PORT=3001 .venv/bin/python app.py
```

Stop with Ctrl+C and rerun the start command to restart. The app reads `.env` at startup; exported environment variables take precedence. Restart after changing environment settings.

## Configuration

| Variable | Purpose and default |
| --- | --- |
| `OCI_ROUTING_PROFILE_ID` | Initial routing-profile OCID. The page also accepts profile edits. |
| `OCI_REGION` | Fallback endpoint region when the selected identifier has no region. Default: `us-chicago-1`. A regional routing-profile OCID takes precedence. |
| `OCI_GENAI_API_KEY` | OCI Generative AI API key for the OpenAI, LangChain, and Agents workflows. Never commit it. |
| `OCI_GENAI_PROJECT_ID` | Project OCID. The app currently requires this and the API key before allowing inference, including the OCI SDK experiment. |
| `OCI_COMPARTMENT_ID` | Compartment OCID used by native OCI SDK inference. |
| `OCI_ROUTING_PROFILE_COMPARTMENT_ID` | Optional native OCI SDK request compartment override. Defaults to `OCI_COMPARTMENT_ID`; keep that variable set. |
| `OCI_CONFIG_FILE` | Signing configuration file for profile validation and native OCI SDK inference. Default: `~/.oci/config`. |
| `OCI_CLI_PROFILE` | Profile name in the OCI configuration file. Default: `DEFAULT`. |
| `OCI_MODEL_ID` | Model fallback when no routing profile is selected or configured. Default: `openai.gpt-oss-120b`. |
| `PORT` | Server port. Default: `3000`. |

The API-key principal needs inference access and routing-profile read permission. The OCI signing identity also needs access to the profile and the inference operation it performs.

## Using the app

1. Check the routing-profile OCID. Click **✎** to edit it, then **✓** to apply the change and reload its policy evidence.
2. Use **Validate profile** to refresh the lifecycle state, inference endpoint region, approved model, allowed serving regions, and compartment.
3. Edit the prompt. The equivalent Python sample updates with the prompt, profile, and derived region.
4. Click **Run once** for a single direct OpenAI Responses request. This button always uses direct inference.
5. For an experiment, choose one of the four SDK tabs, set the request count and concurrency, then click **Run experiment**. The sample code follows the selected tab.
6. Open **View** beside a completion in the execution log to inspect its details. Use **Copy** to copy the current Python sample.

Experiments accept 1–24 requests with concurrency of 1–6. Results show successes, observed serving regions, median latency, policy comparison, and a latency chart. Experiments send real model traffic and produce model usage.

**Cancel run** preserves collected results and cancels queued work where possible. Requests already sent to OCI can continue after cancellation.

Applying a profile changes the current page's requests without rewriting `.env`. Set `OCI_ROUTING_PROFILE_ID` there and restart to change the initial profile after a page reload.

## Automatic endpoint region

The app derives the request endpoint region from the selected routing-profile OCID. For example:

```text
Profile:  ocid1.generativeairoutingprofile.oc1.eu-frankfurt-1.<resource-id>
Endpoint: https://inference.generativeai.eu-frankfurt-1.oci.oraclecloud.com/20231130/actions/v1
```

Changing the profile updates the displayed code and actual request clients for all four SDK modes. Native OCI SDK inference and control-plane profile reads use the derived region, overriding the signing configuration's region for those calls. Recognized short region codes are expanded through the OCI SDK's region aliases.

`OCI_REGION` is used only when the selected identifier has no region. There is no editable region field or region-update API. Legacy `.oci-region` files are ignored.

The endpoint region is where the application submits its request. OCI chooses the serving region from the profile's allowed regions. The app records that selection from `x-genai-selected-region`; it does not choose an allowed serving region itself.

## Completion logs and View

Every collected completion, including individual experiment results, has a **View** link. Failed calls also have a detail entry. The panel includes:

- Input: workflow, prompt, model/profile, derived region, and endpoint. Native OCI SDK calls include the compartment and generation settings.
- Output: returned text or error, response ID, usage when supplied, serving region, latency, and captured response headers.
- HTTP attempts: timestamps, method, URL, submitted JSON body, redacted request headers, response status, and response headers for the OpenAI, LangChain, and Agents clients.
- Retry details: observed attempt count and retries inferred from those attempts.

Native OCI SDK transport attempts and request headers are not captured; its returned response headers are available. Retry summaries describe client HTTP attempts and do not expose OCI's internal routing or retry decisions. Multiple HTTP calls in an agent workflow can also increase the observed attempt count.

Logs retain the latest 80 entries in server memory and reset when the server restarts. A missing serving-region header appears as **not supplied**.

## Policy validation

**Validate profile** reads the profile's current policies using OCI request signing. The experiment compares returned serving-region headers against the loaded allowlist.

**FAIL** means an observed serving region is outside that allowlist. **PASS** means no mismatch was found among the observed headers. Missing headers, an unavailable policy, or failed requests limit what the comparison establishes; review the success count and completion details alongside the result.

## Terraform infrastructure

The infrastructure creates an `oci_generative_ai_routing_profile` and, by default, an IAM policy scoped to the selected compartment for `generativeaiapikey` principals. It requires Terraform 1.5.7 or later and OCI provider version 9.7.0 or later, below 10.0.0.

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars before applying.
terraform init
terraform plan
terraform apply
terraform output -raw routing_profile_id
```

| Setting | Purpose |
| --- | --- |
| `tenancy_id` | Tenancy that owns the IAM policy. Required when `create_api_key_policy` is true. |
| `compartment_id` | Compartment where the new routing profile is created. |
| `model_id` | Supported on-demand model allowed by the profile. |
| `target_regions` | Allowed serving regions, all in one realm and offering the chosen model. |
| `oci_cli_profile` | Configuration profile used by the Terraform provider. Default: `DEFAULT`. Its region determines where the profile is created. |
| `policy_compartment_id` | Leave empty to grant access in `compartment_id`. Set another OCID when granting access to an existing profile owned there. |
| `create_api_key_policy` | Whether to create the API-key IAM policy. Default: `true`. Set `false` when permissions are managed separately. |

Copy the `routing_profile_id` output into `OCI_ROUTING_PROFILE_ID` in `.env`. Setting `policy_compartment_id` changes the policy scope; it does not import or move an existing routing profile into Terraform.

Terraform state, local variable files, and `.env` are excluded from version control by `.gitignore`.

## Local API

| Method and path | Purpose |
| --- | --- |
| `GET /api/config` | Initial profile, derived and fallback regions, region aliases, model fallback, and credential readiness. The API key is omitted. |
| `GET /api/profile?profileId=<OCID>` | Profile state, approved models, allowed serving regions, compartment, and control-plane/inference region. Defaults to the configured profile when `profileId` is omitted. |
| `GET /api/logs` | Latest server log entries, including completion detail records. |
| `POST /api/chat` | One completion. Requires `prompt`; accepts `routingProfileId`, `model`, and `task` (default: `direct`). |
| `POST /api/experiment` | An experiment. Accepts `prompt`, `routingProfileId`, `task`, `count` (default: 6), `concurrency` (default: 2), and optional `runId`. |
| `POST /api/experiment/cancel` | Requests cancellation of the active experiment identified by `runId`. |

POST requests use JSON with `Content-Type: application/json`. Supported task values are `direct`, `langchain`, `agents-sdk`, and `oci-sdk`. The region is derived on the server from the selected profile rather than supplied in the request body.

Example experiment body:

```json
{
  "prompt": "Explain regional routing in one sentence.",
  "routingProfileId": "ocid1.generativeairoutingprofile.oc1.us-chicago-1.replace-me",
  "task": "direct",
  "count": 6,
  "concurrency": 2
}
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Credentials are missing | Set `OCI_GENAI_API_KEY` and `OCI_GENAI_PROJECT_ID`, then restart. |
| Profile evidence is unavailable | Check the OCID, its region, `OCI_CONFIG_FILE`, `OCI_CLI_PROFILE`, and the signing identity's profile-read permission. |
| Inference is rejected | Inspect **View** for status and headers; check API-key permissions in the profile's owning compartment. |
| Native OCI SDK inference fails | Check signing credentials and compartment variables. This mode uses OCI signing. |
| Sample shows an unexpected endpoint | Check the region component of the selected OCID. `OCI_REGION` is only the fallback for regionless identifiers. |
| Serving-region evidence is missing | Inspect response headers in **View**. The app cannot establish that response's serving region without the header. |
| Profile edit disappears after reload | Update `OCI_ROUTING_PROFILE_ID` in `.env` and restart to change the initial profile. |

## References

- [OCI routing profiles](https://docs.oracle.com/en-us/iaas/Content/generative-ai/routing-profile.htm)
- [Routing-profile API permissions](https://docs.oracle.com/en-us/iaas/Content/generative-ai/routing-profile-permissions.htm)
- [OCI API-key permissions](https://docs.oracle.com/en-us/iaas/Content/generative-ai/add-api-permission.htm)
- [OCI Python SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/index.html)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
