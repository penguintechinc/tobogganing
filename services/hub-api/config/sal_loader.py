"""Secrets loading for Tobogganing Hub API via penguin-sal.

Strategy
--------
When ``K8S_NAMESPACE`` is set in the environment the K8s Secrets adapter is
used, reading secrets from the namespace specified by that variable.

When ``K8S_NAMESPACE`` is absent (local dev, CI, or any non-K8s deployment)
every secret falls back to a plain environment variable read.

The three secrets managed here are:

* ``JWT_SECRET_KEY``   – signing key for internal JWTs
* ``DB_PASS``          – database password
* ``REDIS_PASSWORD``   – Redis/Valkey password

Callers
-------
Call :func:`load_secrets` once at startup (inside ``@app.before_serving``
in ``main.py``) and then read the results from :data:`secrets` which is a
plain dict.  Never read these secrets before ``load_secrets`` is called.

Example::

    from config.sal_loader import load_secrets, secrets

    # In startup handler:
    load_secrets()

    # Elsewhere:
    jwt_key = secrets["JWT_SECRET_KEY"]
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Module-level dict populated by load_secrets().  Treat as read-only
# after startup.
secrets: dict[str, str] = {}

# The secret keys hub-api needs.
_REQUIRED_SECRETS: tuple[str, ...] = (
    "JWT_SECRET_KEY",
    "DB_PASS",
    "REDIS_PASSWORD",
)


def _load_from_env() -> dict[str, str]:
    """Read secrets directly from environment variables.

    Returns a dict of ``{key: value}`` for all managed secrets that are
    present in the environment.  Missing keys are omitted and callers
    may decide whether to treat that as an error.
    """
    result: dict[str, str] = {}
    for key in _REQUIRED_SECRETS:
        value = os.getenv(key)
        if value is not None:
            result[key] = value
    return result


def _load_from_k8s(namespace: str) -> dict[str, str]:
    """Read secrets from Kubernetes Secrets via penguin-sal.

    Falls back to the environment variable for any individual secret that
    the K8s adapter fails to retrieve (e.g. secret not yet created).

    Args:
        namespace: The Kubernetes namespace to read secrets from.

    Returns:
        Dict of ``{key: value}`` for all managed secrets.
    """
    try:
        from penguin_sal.adapters import get_adapter_class
        from penguin_sal.core.types import ConnectionConfig
        from penguin_sal.core.exceptions import SecretNotFoundError  # type: ignore[attr-defined]
    except ImportError as exc:
        logger.warning(
            "penguin-sal not available (%s); falling back to env vars", exc
        )
        return _load_from_env()

    # k8s://namespace?context=<ctx> — context is optional; defaults to
    # in-cluster config when running inside a Pod.
    k8s_context = os.getenv("K8S_CONTEXT", "")
    uri_params: dict[str, str] = {}
    if k8s_context:
        uri_params["context"] = k8s_context

    conn_config = ConnectionConfig(
        scheme="k8s",
        host=namespace,
        params=uri_params,
    )

    adapter_class = get_adapter_class("k8s")
    result: dict[str, str] = {}

    try:
        adapter = adapter_class(conn_config)
        adapter.authenticate()

        for key in _REQUIRED_SECRETS:
            try:
                secret_obj = adapter.get(key)
                value = secret_obj.value
                if isinstance(value, bytes):
                    result[key] = value.decode()
                elif isinstance(value, dict):
                    # Some K8s secrets store a JSON dict; try "value" key.
                    result[key] = str(value.get("value", ""))
                else:
                    result[key] = str(value)
                logger.debug("Loaded secret '%s' from K8s namespace '%s'", key, namespace)
            except Exception as secret_exc:
                logger.warning(
                    "Could not load '%s' from K8s (%s); trying env var",
                    key,
                    secret_exc,
                )
                env_val = os.getenv(key)
                if env_val is not None:
                    result[key] = env_val

        adapter.close()
    except Exception as adapter_exc:
        logger.error(
            "K8s secrets adapter failed (%s); falling back entirely to env vars",
            adapter_exc,
        )
        return _load_from_env()

    return result


def load_secrets() -> None:
    """Load all managed secrets into the module-level :data:`secrets` dict.

    Call once during application startup.  Subsequent calls are idempotent
    and refresh the cached values.

    Backend selection
    -----------------
    * ``K8S_NAMESPACE`` set  → Kubernetes Secrets adapter via penguin-sal
    * ``K8S_NAMESPACE`` unset → environment variable fallback

    Raises:
        RuntimeError: If a required secret is missing from both the backend
                      and the environment.
    """
    global secrets  # noqa: PLW0603

    namespace = os.getenv("K8S_NAMESPACE", "")

    if namespace:
        logger.info("Loading secrets from Kubernetes namespace '%s'", namespace)
        loaded = _load_from_k8s(namespace)
    else:
        logger.info("K8S_NAMESPACE not set; loading secrets from environment variables")
        loaded = _load_from_env()

    # Validate all required secrets are present.
    missing = [k for k in _REQUIRED_SECRETS if k not in loaded or not loaded[k]]
    if missing:
        raise RuntimeError(
            f"Required secrets not available: {missing}. "
            "Set the corresponding environment variables or ensure the K8s "
            "Secrets exist in the target namespace."
        )

    secrets = loaded
    logger.info("Secrets loaded successfully (%d keys)", len(secrets))


def get_secret(key: str) -> str:
    """Retrieve a named secret from the loaded cache.

    Args:
        key: One of the managed secret keys.

    Returns:
        The secret value string.

    Raises:
        KeyError:    If the key is not one of the managed secrets.
        RuntimeError: If :func:`load_secrets` has not been called yet.
    """
    if not secrets:
        raise RuntimeError("load_secrets() must be called before accessing secrets.")
    if key not in secrets:
        raise KeyError(f"Unknown secret key: '{key}'")
    return secrets[key]
