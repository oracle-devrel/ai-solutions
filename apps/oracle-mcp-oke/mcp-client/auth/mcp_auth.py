import urllib.error
import urllib.parse
import urllib.request
import json
from typing import Any

from agent_common.config import env_bool, get_env


def _require_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise RuntimeError(f"{name} is required when MCP auth is enabled")
    return value


def _fetch_oauth_access_token(logger: Any | None = None) -> str:
    token_url = _require_env("MCP_AUTH_TOKEN_URL")
    client_id = _require_env("MCP_AUTH_CLIENT_ID")
    client_secret = _require_env("MCP_AUTH_CLIENT_SECRET")
    scope = get_env("MCP_AUTH_SCOPE")
    grant_type = get_env("MCP_AUTH_GRANT_TYPE", "client_credentials") or "client_credentials"
    timeout = float(get_env("MCP_AUTH_TIMEOUT_SECONDS", "15") or "15")

    data: dict[str, str] = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope

    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Failed to fetch MCP OAuth token: HTTP {exc.code} - {error_body[:300]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch MCP OAuth token: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Token endpoint returned non-JSON response") from exc

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Token endpoint response missing access_token")

    if logger:
        logger.info(
            "Fetched MCP OAuth access token using client_credentials flow token_preview=%s length=%s",
            access_token[:16] + ("..." if len(access_token) > 16 else ""),
            len(access_token),
        )
    return access_token


def _normalize_mcp_url(mcp_url: str | None) -> str:
    raw = str(mcp_url or "").strip()
    if not raw:
        raise RuntimeError("MCP_URL is required")

    parsed = urllib.parse.urlsplit(raw)
    path = parsed.path or ""

    # Hosted application MCP endpoints already point to the invoke path and must not
    # be rewritten to a local /mcp route.
    is_hosted_application = "/hostedApplications/" in path and path.rstrip("/").endswith("/actions/invoke/mcp")
    if is_hosted_application:
        return raw

    # For direct FastMCP servers, normalize to a canonical /mcp endpoint.
    normalized_path = path.rstrip("/")
    if not normalized_path or normalized_path == "":
        normalized_path = "/mcp"
    elif not normalized_path.endswith("/mcp"):
        normalized_path = f"{normalized_path}/mcp"

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, parsed.fragment))


def _resolve_mcp_transport(normalized_url: str) -> str:
    """Resolve transport explicitly for the known working cases in this project.

    - Direct/local FastMCP `/mcp` endpoints use `streamable_http`.
    - Hosted Application invoke MCP endpoints use `http` because that has already
      been observed to make tool discovery work for this endpoint shape.

    No general auto-discovery is performed; this is just deterministic routing by
    URL shape, with `MCP_TRANSPORT` still available as an explicit override.
    """
    explicit = (get_env("MCP_TRANSPORT") or "").strip().lower().replace("-", "_")
    if explicit in {"http", "streamable_http", "sse", "stdio", "websocket"}:
        return explicit

    parsed = urllib.parse.urlsplit(normalized_url)
    path = parsed.path or ""
    is_hosted_application = "/hostedApplications/" in path and path.rstrip("/").endswith("/actions/invoke/mcp")
    if is_hosted_application:
        return "http"
    return "http"


def build_mcp_server_config(
    mcp_url: str | None,
    timeout: float = 30.0,
    logger: Any | None = None,
) -> dict[str, Any]:
    normalized_url = _normalize_mcp_url(mcp_url)
    transport = _resolve_mcp_transport(normalized_url)
    config: dict[str, Any] = {
        "transport": transport,
        "url": normalized_url,
        "timeout": timeout,
    }

    if logger and normalized_url != str(mcp_url or "").strip():
        logger.info("Normalized MCP URL from %s to %s", mcp_url, normalized_url)
    if logger:
        logger.info("Using MCP transport=%s for url=%s", transport, normalized_url)

    if not env_bool("MCP_AUTH_ENABLED", False):
        return config

    access_token = get_env("MCP_AUTH_ACCESS_TOKEN")
    if access_token:
        if logger:
            logger.info(
                "MCP auth enabled: using access token from MCP_AUTH_ACCESS_TOKEN token_preview=%s length=%s",
                access_token[:16] + ("..." if len(access_token) > 16 else ""),
                len(access_token),
            )
    else:
        access_token = _fetch_oauth_access_token(logger=logger)

    config["headers"] = {"Authorization": f"Bearer {access_token}"}
    return config
