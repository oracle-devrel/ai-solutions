# MCP Audio Server Tools

This server exposes only two MCP tools:

- `process_audio(object_name=None, file_name=None, audio_base64=None, payload=None)`
- `sentiment_analysis(text)`

## Tool Notes

- Responses are JSON strings.
- `process_audio` accepts either:
  - object mode: `object_name`
  - inline mode: `file_name` + `audio_base64`
- Optional `payload` must be a JSON string.
- Merge precedence is: exact top-level args over payload fields.

## Health Endpoint

- `GET /health` returns `OK`.

## OCI auth behavior

Server runtime auth selection is:

- `ENVIRONMENT=dev` -> local OCI config/profile auth
- otherwise -> OKE workload identity, then resource principal, then instance principal

For local development, keep `ENVIRONMENT=dev` (or `ENVIRONMENT=local`) and set `OCI_CONFIG_PROFILE` / `OCI_CONFIG_FILE` as needed.
Set `OCI_REGION` explicitly when you want local Speech/Object Storage calls to target a region different from the one in your OCI profile.

