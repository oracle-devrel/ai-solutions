const $ = selector => document.querySelector(selector);
let config = {};
let profileEvidence = null;
let selectedTask = 'direct';
let activeRunId = null;

const esc = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const activeProfile = () => $('#profile').value.trim() || config.routingProfileId || '<ROUTING_PROFILE_OCID>';
const activeRegion = () => {
  const profile = activeProfile();
  const region = profile.startsWith('ocid1.generativeairoutingprofile.') ? profile.split('.')[3] : '';
  return config.regionAliases?.[region] || region || config.defaultRegion || config.region || 'us-chicago-1';
};

function sdkSnippet() {
  const region = activeRegion();
  const prompt = $('#prompt').value.replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('\n', '\\n');
  const baseUrl = `https://inference.generativeai.${region}.oci.oraclecloud.com/20231130/actions/v1`;
  const profile = activeProfile();
  if (selectedTask === 'langchain') {
    $('#sdk').textContent = `import os
import httpx
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="${profile}",
    base_url="${baseUrl}",
    api_key=os.environ["OCI_GENAI_API_KEY"],
    http_client=httpx.Client(trust_env=False),
    include_response_headers=True,
    temperature=0,
)

response = model.invoke([
    ("system", "You are a concise regional-routing analyst."),
    ("human", "${prompt}"),
])

print(response.content)
print(response.response_metadata["headers"].get("x-genai-selected-region"))`;
    return;
  }
  if (selectedTask === 'agents-sdk') {
    $('#sdk').textContent = `import asyncio
import os
import httpx
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from openai import AsyncOpenAI

async def main():
    routing_headers = []
    async def capture_headers(response):
        routing_headers.append(dict(response.headers))

    client = AsyncOpenAI(
        base_url="${baseUrl}",
        api_key=os.environ["OCI_GENAI_API_KEY"],
        http_client=httpx.AsyncClient(
            trust_env=False,
            event_hooks={"response": [capture_headers]},
        ),
    )
    set_tracing_disabled(True)
    agent = Agent(
        name="Routing validation agent",
        instructions="Answer concisely in one sentence.",
        model=OpenAIChatCompletionsModel(
            model="${profile}", openai_client=client
        ),
    )
    result = await Runner.run(agent, "${prompt}")
    print(result.final_output)
    print(routing_headers[-1].get("x-genai-selected-region"))
    await client.close()

asyncio.run(main())`;
    return;
  }
  if (selectedTask === 'oci-sdk') {
    $('#sdk').textContent = `import os
import oci

# Uses OCI_CONFIG_FILE (default: ~/.oci/config) and DEFAULT.
config = oci.config.from_file(
    file_location=os.path.expanduser(
        os.getenv("OCI_CONFIG_FILE", "~/.oci/config")
    ),
    profile_name=os.getenv("OCI_CLI_PROFILE", "DEFAULT"),
)
config["region"] = "${region}"
client = oci.generative_ai_inference.GenerativeAiInferenceClient(config)

response = client.chat(
    oci.generative_ai_inference.models.ChatDetails(
        compartment_id=os.environ["OCI_ROUTING_PROFILE_COMPARTMENT_ID"],
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            model_id="${profile}",
        ),
        chat_request=oci.generative_ai_inference.models.GenericChatRequest(
            messages=[oci.generative_ai_inference.models.UserMessage(
                content=[oci.generative_ai_inference.models.TextContent(
                    text="${prompt}",
                )]
            )],
            temperature=0,
        ),
    )
)

print(response.data.chat_response.choices[0].message.content[0].text)
print(response.headers.get("x-genai-selected-region"))`;
    return;
  }
  $('#sdk').textContent = `import os
import httpx2
from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}",
    api_key=os.environ["OCI_GENAI_API_KEY"],
    http_client=httpx2.Client(trust_env=False),
)

response = client.responses.create(
    model="${profile}",
    input="${prompt}",
)

print(response.output_text)`;
}

async function request(path, body) {
  const response = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

async function loadProfile() {
  const profileId = activeProfile();
  profileEvidence = null;
  $('#profile-state').textContent = 'Loading…';
  try {
    const evidence = await fetch(`/api/profile?profileId=${encodeURIComponent(profileId)}`).then(async response => {
      const data = await response.json(); if (!response.ok) throw new Error(data.error); return data;
    });
    if (activeProfile() !== profileId) return;
    profileEvidence = evidence;
    sdkSnippet();
    $('#profile-state').textContent = profileEvidence.state;
    $('#profile-state').className = `pill ${profileEvidence.state === 'ACTIVE' ? 'good' : ''}`;
    $('#profile-details').innerHTML = `<div class="evidence-row"><span>Inference endpoint region</span><code>${esc(profileEvidence.inferenceRegion)}</code></div><div class="evidence-row"><span>Approved model</span><code>${esc(profileEvidence.allowedModels.join(', '))}</code></div><div class="evidence-row"><span>Allowed regions</span><div>${profileEvidence.allowedRegions.map(region => `<span class="region-tag">${esc(region)}</span>`).join('')}</div></div><div class="evidence-row"><span>Profile scope</span><code>${esc(profileEvidence.compartmentId)}</code></div>`;
  } catch (error) {
    if (activeProfile() !== profileId) return;
    $('#profile-state').textContent = 'Unavailable'; $('#profile-state').className = 'pill bad';
    $('#profile-details').textContent = error.message;
  }
}

async function refreshLogs() {
  const data = await fetch('/api/logs').then(response => response.json());
  $('#loglines').innerHTML = data.length ? data.map(item => {
    const summary = `<time>${new Date(item.at).toLocaleTimeString()}</time><strong class="${item.level}">${item.level.toUpperCase()}</strong> ${esc(item.message)}${item.selectedRegion ? ` · <span class="region-text">${esc(item.selectedRegion)}</span>` : ''}${item.elapsedMs ? ` · ${item.elapsedMs} ms` : ''}`;
    if (!item.trace) return `<p class="log-line">${summary}</p>`;
    const section = (heading, value) => `<h3>${heading}</h3><pre>${esc(JSON.stringify(value, null, 2))}</pre>`;
    return `<div class="log-entry"><div class="log-line">${summary}<a href="#" class="log-view" aria-expanded="false">View</a></div><div class="log-output" hidden>${section('Input', item.trace.input)}${section('Output', item.trace.output)}${section('HTTP attempts and headers', item.trace.attempts)}${section('Retry details', item.trace.retryDetails)}</div></div>`;
  }).join('') : 'No activity yet.';
}

$('#loglines').addEventListener('click', event => {
  const link = event.target.closest('.log-view');
  if (!link) return;
  event.preventDefault();
  const output = link.closest('.log-entry').querySelector('.log-output');
  output.hidden = !output.hidden;
  link.textContent = output.hidden ? 'View' : 'Hide';
  link.setAttribute('aria-expanded', String(!output.hidden));
});

function setBusy(button, busy, label) { button.disabled = busy; if (busy) button.dataset.label = button.textContent; button.textContent = busy ? label : button.dataset.label; }

async function runOne() {
  const button = $('#run'); setBusy(button, true, 'Running…');
  try {
    await request('/api/chat', { prompt: $('#prompt').value, routingProfileId: $('#profile').value });
  } catch (error) { $('#loglines').innerHTML = `<p class="log-line error">Single request failed: ${esc(error.message)}</p>`; }
  finally { setBusy(button, false); refreshLogs(); }
}

function renderExperiment(data) {
  const successful = data.results.filter(result => result.ok);
  const selected = successful.filter(result => result.selectedRegion);
  const allowed = profileEvidence?.allowedRegions || [];
  const buckets = selected.reduce((all, result) => ({ ...all, [result.selectedRegion]: (all[result.selectedRegion] || 0) + 1 }), {});
  const elapsed = successful.map(result => result.elapsedMs).sort((a, b) => a - b);
  const median = elapsed.length ? elapsed[Math.floor(elapsed.length / 2)] : 0;
  const outOfPolicy = selected.filter(result => allowed.length && !allowed.includes(result.selectedRegion));
  $('#experiment-summary').innerHTML = `<div class="task-result">Task: ${esc(data.task)}</div><div class="metrics"><div><b>${successful.length}/${data.count}</b><span>successful</span></div><div><b>${Object.keys(buckets).length}</b><span>regions observed</span></div><div><b>${median} ms</b><span>median latency</span></div><div><b class="${outOfPolicy.length ? 'invalid' : 'valid'}">${outOfPolicy.length ? 'FAIL' : 'PASS'}</b><span>policy validation</span></div></div><div class="distribution">${Object.entries(buckets).map(([region, count]) => `<div><span>${esc(region)}</span><b>${count}</b><i style="width:${Math.max(12, (count / successful.length) * 100)}%"></i></div>`).join('') || '<span>No serving-region header returned.</span>'}</div>`;
  $('#experiment-results').innerHTML = `<div class="run-table"><div class="run-head"><span>#</span><span>Serving region</span><span>Latency</span><span>Evidence</span></div>${data.results.map(result => result.ok ? `<div class="run-row"><span>${result.sequence}</span><span class="${allowed.length && !allowed.includes(result.selectedRegion) ? 'invalid' : 'valid'}">${esc(result.selectedRegion || 'not supplied')}</span><span>${result.elapsedMs} ms</span><code title="${esc(result.ociMetadata?.['opc-request-id'] || '')}">${esc(result.id)}</code></div>` : `<div class="run-row failed"><span>${result.sequence}</span><span>Failed</span><span>—</span><code>${esc(result.error)}</code></div>`).join('')}</div>`;
  const palette = ['#c74634', '#f29111', '#4b7d6b', '#7a6ff0', '#3a92a8'];
  const regionColors = Object.fromEntries(Object.keys(buckets).map((region, index) => [region, palette[index % palette.length]]));
  const maximum = Math.max(...successful.map(result => result.elapsedMs), 1);
  $('#latency-chart').classList.remove('empty');
  const width = Math.max(420, successful.length * 72), height = 180, padding = 24;
  const points = successful.map((result, index) => ({ ...result, x: padding + index * ((width - padding * 2) / Math.max(successful.length - 1, 1)), y: height - padding - ((result.elapsedMs / maximum) * (height - padding * 2)) }));
  const line = points.map(point => `${point.x},${point.y}`).join(' ');
  $('#latency-chart').innerHTML = successful.length ? `<div class="chart-title"><span>Latency by response</span><small>Line = latency trend · point color = OCI selected region</small></div><div class="line-graph"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Latency line graph">${[0.25,0.5,0.75].map(level => `<line x1="${padding}" x2="${width-padding}" y1="${height-padding-(level*(height-padding*2))}" y2="${height-padding-(level*(height-padding*2))}"/>`).join('')}<polyline points="${line}"/>${points.map(point => `<g><circle cx="${point.x}" cy="${point.y}" r="5" fill="${regionColors[point.selectedRegion] || '#617b78'}"><title>#${point.sequence} · ${point.elapsedMs} ms · ${esc(point.selectedRegion)}</title></circle><text x="${point.x}" y="${height-7}" text-anchor="middle">#${point.sequence}</text></g>`).join('')}</svg></div><div class="chart-legend">${Object.entries(regionColors).map(([region, color]) => `<span><i style="background:${color}"></i>${esc(region)}</span>`).join('')}</div>` : 'No successful responses to chart.';
}

async function runExperiment() {
  const button = $('#experiment-run'); activeRunId = crypto.randomUUID(); setBusy(button, true, 'Running live…'); $('#experiment-cancel').disabled = false; $('#experiment-summary').textContent = 'Sending requests and collecting serving-region headers…'; $('#experiment-results').innerHTML = '';
  try {
    const data = await request('/api/experiment', { runId: activeRunId, task: selectedTask, prompt: $('#prompt').value, routingProfileId: $('#profile').value, count: Number($('#count').value), concurrency: Number($('#concurrency').value) });
    renderExperiment(data);
    if (data.cancelled) $('#experiment-summary').insertAdjacentHTML('afterbegin', '<p class="cancelled">Cancelled: completed responses are retained below.</p>');
  } catch (error) { $('#experiment-summary').textContent = `Experiment failed: ${error.message}`; }
  finally { activeRunId = null; $('#experiment-cancel').disabled = true; setBusy(button, false); refreshLogs(); }
}

async function init() {
  config = await fetch('/api/config').then(response => response.json());
  $('#status').textContent = config.configured ? 'Server credential ready' : 'Configure environment'; $('#status').classList.toggle('ready', config.configured);
  $('#profile').value = config.routingProfileId || '';
  sdkSnippet(); loadProfile();
}

$('#profile').addEventListener('input', () => { profileEvidence = null; sdkSnippet(); });
$('#edit-profile').onclick = () => { const input = $('#profile'); const editing = input.hasAttribute('readonly'); input.toggleAttribute('readonly', !editing); $('#edit-profile').textContent = editing ? '✓' : '✎'; $('#edit-profile').title = editing ? 'Apply routing profile' : 'Edit routing profile'; if (editing) input.focus(); else loadProfile(); sdkSnippet(); };
$('#prompt').addEventListener('input', sdkSnippet);
$('#copy').onclick = () => navigator.clipboard.writeText($('#sdk').textContent);
$('#refresh').onclick = refreshLogs;
$('#run').onclick = runOne;
$('#load-profile').onclick = loadProfile;
$('#experiment-run').onclick = runExperiment;
$('#experiment-cancel').onclick = async () => { if (!activeRunId) return; $('#experiment-cancel').disabled = true; $('#experiment-cancel').textContent = 'Cancelling…'; try { await request('/api/experiment/cancel', { runId: activeRunId }); $('#experiment-summary').textContent = 'Cancellation requested; completed responses will be retained.'; } catch (error) { $('#experiment-summary').textContent = `Could not cancel: ${error.message}`; } finally { $('#experiment-cancel').textContent = 'Cancel run'; } };
document.querySelectorAll('.task').forEach(button => button.onclick = () => { selectedTask = button.dataset.task; document.querySelectorAll('.task').forEach(item => item.classList.toggle('active', item === button)); sdkSnippet(); });
init();
