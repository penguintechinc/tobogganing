"""OpenAPI spec generation shared by /openapi.json and scripts/generate_openapi.py.

Derives the spec from quart-schema so it cannot drift from the code, then
normalises quart-schema output to valid OpenAPI 3.x.
"""

from __future__ import annotations

from typing import Any

from quart import Quart


def sanitize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Fix quart-schema serialization quirks in place and return the spec.

    Renames bearer_format -> bearerFormat and drops meaningless default: null.
    """

    def _walk(obj: dict[str, Any]) -> None:
        """Recursively apply fixes to a nested dict."""
        schemes = obj.get("securitySchemes")
        if isinstance(schemes, dict):
            for scheme in schemes.values():
                if isinstance(scheme, dict) and "bearer_format" in scheme:
                    scheme["bearerFormat"] = scheme.pop("bearer_format")
        if "default" in obj and obj["default"] is None:
            del obj["default"]
        for v in obj.values():
            if isinstance(v, dict):
                _walk(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _walk(item)

    _walk(spec)
    return spec


async def build_spec(app: Quart) -> dict[str, Any]:
    """Build the full OpenAPI spec for all currently registered routes.

    Must be called within a request context (quart-schema reads url_map there).
    """
    if "QUART_SCHEMA" not in app.extensions:
        raise RuntimeError("QuartSchema not initialized on app")
    response = await app.extensions["QUART_SCHEMA"].openapi()
    spec: dict[str, Any] = await response.get_json()
    info = spec.setdefault("info", {})
    info.setdefault("title", app.config.get("PRODUCT_NAME", "Hub API"))
    info.setdefault("version", "1.0.0")
    return sanitize_spec(spec)
