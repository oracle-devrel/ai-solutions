import os
from typing import Any

import oci

from agent_common.config import get_env


def load_dev_oci_config_and_signer(
    logger,
    connection_timeout: float = 10.0,
    read_timeout: float = 120.0,
) -> tuple[dict[str, Any], Any | None]:
    """Load OCI config/signer using the same auth selection approach as mcp-server/tools/oci_auth.py.

    Behavior:
    - Load the configured profile (AUTH_PROFILE, default DEFAULT).
    - If security_token_file exists -> use SecurityTokenSigner.
    - Else if key_file exists -> use config-based auth.
    """

    configured_profile = str(get_env("AUTH_PROFILE", "DEFAULT") or "DEFAULT").strip()
    config_file = os.path.expanduser(str(get_env("OCI_CONFIG_FILE", "~/.oci/config") or "~/.oci/config"))

    def _load_profile(profile_name: str) -> dict[str, Any]:
        cfg = oci.config.from_file(file_location=config_file, profile_name=profile_name)
        cfg["connection_timeout"] = connection_timeout
        cfg["read_timeout"] = read_timeout
        return cfg

    config = _load_profile(configured_profile)
    region_from_env = str(get_env("OCI_REGION") or "").strip()
    if region_from_env:
        config["region"] = region_from_env
    token_file = os.path.expanduser(config.get("security_token_file", "")).strip()
    key_file = os.path.expanduser(config.get("key_file", "")).strip()

    if token_file:
        if not key_file:
            raise RuntimeError(
                f"OCI profile '{configured_profile}' sets security_token_file but key_file is missing"
            )
        if not os.path.isfile(token_file) or not os.path.isfile(key_file):
            raise RuntimeError(
                f"OCI profile '{configured_profile}' token/key file does not exist: "
                f"token_file='{token_file}', key_file='{key_file}'"
            )

        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()

        private_key = oci.signer.load_private_key_from_file(key_file)
        signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
        logger.info(
            "OCI config loaded from profile '%s' using security token signer, region=%s",
            configured_profile,
            config.get("region"),
        )
        return config, signer

    if key_file and os.path.isfile(key_file):
        logger.info(
            "OCI config loaded from profile '%s' using key_file auth, region=%s",
            configured_profile,
            config.get("region"),
        )
        return config, None

    raise RuntimeError(
        f"OCI profile '{configured_profile}' is not usable: neither valid key_file "
        "nor security_token_file/key_file pair found"
    )


def _is_dev_environment() -> bool:
    environment = str(get_env("ENVIRONMENT") or "").strip().lower()
    if environment in {"dev", "local"}:
        return True
    if environment:
        return False

    # ENVIRONMENT is unset: treat as local dev mode only when OCI config exists.
    config_file = os.path.expanduser(str(get_env("OCI_CONFIG_FILE", "~/.oci/config") or "~/.oci/config"))
    return os.path.isfile(config_file)


def _runtime_local_config_mode() -> str | None:
    if _is_dev_environment():
        return "dev"

    return None


def load_runtime_oci_config_and_signer(
    logger,
    connection_timeout: float = 10.0,
    read_timeout: float = 120.0,
) -> tuple[dict[str, Any], Any | None, str]:
    """Load runtime OCI auth with env-based strategy.

    Strategy:
    - First, if we are in dev,
      use config-file profile auth.
    - Otherwise: try OKE workload identity first, then OCI resource principal,
      then instance principal.
    """
    env_value = str(get_env("ENVIRONMENT") or "").strip()
    configured_profile = str(get_env("AUTH_PROFILE", "DEFAULT") or "DEFAULT").strip()
    configured_config_file = os.path.expanduser(str(get_env("OCI_CONFIG_FILE", "~/.oci/config") or "~/.oci/config"))
    local_config_mode = _runtime_local_config_mode()
    region_from_env = str(get_env("OCI_REGION") or "").strip() or None

    logger.info("Runtime auth resolver ENVIRONMENT=%s", env_value or "<unset>")

    if local_config_mode:
        config, signer = load_dev_oci_config_and_signer(
            logger=logger,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
        )
        logger.info(
            "Runtime OCI auth selected mode=%s region=%s profile=%s config_file=%s",
            local_config_mode,
            config.get("region"),
            configured_profile,
            configured_config_file,
        )
        return config, signer, local_config_mode

    try:
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        return {"region": region}, signer, "oke_workload"
    except Exception as exc:
        logger.info("OKE workload signer unavailable, trying resource principal: %s", exc)

    try:
        signer = oci.auth.signers.get_resource_principals_signer()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        return {"region": region}, signer, "resource_principal"
    except Exception as exc:
        logger.info("Resource principal signer unavailable, trying instance principal: %s", exc)

    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        return {"region": region}, signer, "instance_principal"
    except Exception as exc:
        raise RuntimeError(
            "No runtime OCI auth mode available. Checked: OKE workload, resource principal, instance principal."
        ) from exc
