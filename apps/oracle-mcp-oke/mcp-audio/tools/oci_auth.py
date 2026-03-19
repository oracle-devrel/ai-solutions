import os
from typing import Any

import oci


def _safe_region(value: Any) -> str:
    return str(value or "").strip() or "<unknown>"


def _safe_signer_type(signer: Any | None) -> str:
    if signer is None:
        return "none"
    return signer.__class__.__name__


def _signer_debug_details(signer: Any | None) -> dict[str, str]:
    if signer is None:
        return {"signer_type": "none"}
    tenancy_id = ""
    try:
        tenancy_id = str(getattr(signer, "tenancy_id", "") or getattr(signer, "tenancy", "") or "").strip()
    except Exception:
        tenancy_id = ""
    return {
        "signer_type": _safe_signer_type(signer),
        "region": _safe_region(getattr(signer, "region", None)),
        "tenancy_id_prefix": tenancy_id[:24] + ("..." if tenancy_id else ""),
    }


def load_dev_oci_config_and_signer(
    expanded_config_file: str,
    logger,
    connection_timeout: float = 10.0,
    read_timeout: float = 240.0,
) -> tuple[dict[str, Any], Any | None]:
    """Load OCI config/signer for dev/config-file mode.

    Behavior:
    - Load the configured profile (OCI_CONFIG_PROFILE, default DEFAULT).
    - If security_token_file exists: build SecurityTokenSigner.
    - Else if key_file exists: use config-based auth.
    """

    configured_profile = os.environ.get("OCI_CONFIG_PROFILE", "").strip()

    def _load_profile(profile_name: str) -> dict[str, Any]:
        cfg = oci.config.from_file(file_location=expanded_config_file, profile_name=profile_name)
        cfg["connection_timeout"] = connection_timeout
        cfg["read_timeout"] = read_timeout
        return cfg

    profile_name = configured_profile or "DEFAULT"
    config = _load_profile(profile_name)
    region_from_env = (os.getenv("OCI_REGION") or "").strip()
    if region_from_env:
        config["region"] = region_from_env
    token_file = os.path.expanduser(config.get("security_token_file", "")).strip()
    key_file = os.path.expanduser(config.get("key_file", "")).strip()

    if token_file:
        if not key_file:
            raise RuntimeError(
                f"OCI profile '{profile_name}' sets security_token_file but key_file is missing"
            )
        if not os.path.isfile(token_file) or not os.path.isfile(key_file):
            raise RuntimeError(
                f"OCI profile '{profile_name}' token/key file does not exist: "
                f"token_file='{token_file}', key_file='{key_file}'"
            )

        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()

        private_key = oci.signer.load_private_key_from_file(key_file)
        signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
        logger.info(
            f"OCI config loaded from profile '{profile_name}' using security token signer, "
            f"region={config.get('region')}"
        )
        return config, signer

    if key_file and os.path.isfile(key_file):
        logger.info(
            f"OCI config loaded from profile '{profile_name}' using key_file auth, "
            f"region={config.get('region')}"
        )
        return config, None

    raise RuntimeError(
        f"OCI profile '{profile_name}' is not usable: neither valid key_file nor security_token_file/key_file pair found"
    )


def _is_dev_environment() -> bool:
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if environment in {"dev", "local"}:
        return True
    if environment:
        return False

    # ENVIRONMENT is unset: treat as local dev mode only when OCI config exists.
    expanded_config_file = os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
    return os.path.isfile(expanded_config_file)


def _runtime_local_config_mode() -> str | None:
    if _is_dev_environment():
        return "dev"
    return None


def load_runtime_oci_config_and_signer(
    logger,
    connection_timeout: float = 10.0,
    read_timeout: float = 240.0,
) -> tuple[dict[str, Any], Any | None, str]:
    """Load OCI auth for runtime execution.

    Strategy:
    - For local dev mode (ENVIRONMENT=dev/local, or ENVIRONMENT unset with local OCI config present):
      use config-file profile auth.
    - Otherwise: try OKE workload identity, then resource principal,
      then instance principal.
    """
    local_config_mode = _runtime_local_config_mode()

    if local_config_mode:
        expanded_config_file = os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
        config, signer = load_dev_oci_config_and_signer(
            expanded_config_file=expanded_config_file,
            logger=logger,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
        )
        logger.info(
            "Runtime OCI auth selected mode=%s region=%s signer=%s profile=%s config_file=%s",
            local_config_mode,
            _safe_region(config.get("region")),
            _safe_signer_type(signer),
            os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"),
            expanded_config_file,
        )
        return config, signer, local_config_mode

    region_from_env = (os.getenv("OCI_REGION") or "").strip() or None
    logger.info(
        "Runtime OCI auth resolving non-dev mode environment=%s OCI_REGION=%s",
        (os.getenv("ENVIRONMENT") or "").strip() or "<unset>",
        region_from_env or "<unset>",
    )

    try:
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        logger.info(
            "Runtime OCI auth selected mode=oke_workload details=%s",
            _signer_debug_details(signer),
        )
        return {"region": region}, signer, "oke_workload"
    except Exception as exc:
        logger.info("OKE workload signer unavailable, trying resource principal: %s", exc)

    try:
        signer = oci.auth.signers.get_resource_principals_signer()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        logger.info(
            "Runtime OCI auth selected mode=resource_principal details=%s",
            _signer_debug_details(signer),
        )
        return {"region": region}, signer, "resource_principal"
    except Exception as exc:
        logger.info("Resource principal signer unavailable, trying instance principal: %s", exc)

    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        region = region_from_env or getattr(signer, "region", None) or "us-chicago-1"
        logger.info(
            "Runtime OCI auth selected mode=instance_principal details=%s",
            _signer_debug_details(signer),
        )
        return {"region": region}, signer, "instance_principal"
    except Exception as exc:
        raise RuntimeError(
            "No runtime OCI auth mode available. Checked: OKE workload, resource principal, instance principal."
        ) from exc
