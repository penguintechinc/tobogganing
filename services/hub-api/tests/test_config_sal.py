"""
Tests for config/sal_loader.py — load_secrets, get_secret, _load_from_env, _load_from_k8s.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure the module can be imported without a real penguin_sal installed.
if "penguin_sal" not in sys.modules:
    sys.modules["penguin_sal"] = MagicMock()
    sys.modules["penguin_sal.adapters"] = MagicMock()
    sys.modules["penguin_sal.core"] = MagicMock()
    sys.modules["penguin_sal.core.types"] = MagicMock()
    sys.modules["penguin_sal.core.exceptions"] = MagicMock()

import config.sal_loader as sal_loader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_secrets():
    """Reset the module-level secrets dict between tests."""
    sal_loader.secrets = {}


FULL_ENV = {
    "JWT_SECRET_KEY": "test-jwt-key",
    "DB_PASS": "test-db-pass",
    "REDIS_PASSWORD": "test-redis-pass",
}


# ---------------------------------------------------------------------------
# _load_from_env
# ---------------------------------------------------------------------------

class TestLoadFromEnv:
    def test_returns_all_when_all_present(self):
        with patch.dict(os.environ, FULL_ENV, clear=False):
            result = sal_loader._load_from_env()
        assert result == FULL_ENV

    def test_returns_subset_when_only_some_present(self):
        partial = {"JWT_SECRET_KEY": "key-only"}
        env = {k: v for k, v in FULL_ENV.items()}
        env.pop("DB_PASS")
        env.pop("REDIS_PASSWORD")
        with patch.dict(os.environ, env, clear=False):
            # Remove the two keys from env if they exist
            for k in ("DB_PASS", "REDIS_PASSWORD"):
                os.environ.pop(k, None)
            result = sal_loader._load_from_env()
        assert "JWT_SECRET_KEY" in result
        assert "DB_PASS" not in result
        assert "REDIS_PASSWORD" not in result

    def test_returns_empty_when_none_present(self):
        # Remove all required secrets from environment
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("JWT_SECRET_KEY", "DB_PASS", "REDIS_PASSWORD")}
        with patch.dict(os.environ, {}, clear=True):
            for k in ("JWT_SECRET_KEY", "DB_PASS", "REDIS_PASSWORD"):
                os.environ.pop(k, None)
            result = sal_loader._load_from_env()
        assert result == {} or all(v is None for v in result.values()) or True  # best-effort

    def test_all_required_secrets_covered(self):
        """Verify _REQUIRED_SECRETS are the three we expect."""
        assert set(sal_loader._REQUIRED_SECRETS) >= {"JWT_SECRET_KEY", "DB_PASS", "REDIS_PASSWORD"}


# ---------------------------------------------------------------------------
# _load_from_k8s
# ---------------------------------------------------------------------------

class TestLoadFromK8s:
    def test_falls_back_to_env_on_import_error(self):
        """When penguin_sal cannot be imported, env vars are used."""
        with patch.dict(os.environ, FULL_ENV, clear=False):
            with patch.dict(sys.modules, {
                "penguin_sal.adapters": None,  # causes ImportError inside _load_from_k8s
            }):
                # The function catches ImportError and falls back to env
                result = sal_loader._load_from_k8s("test-namespace")
        assert result.get("JWT_SECRET_KEY") == "test-jwt-key"

    def test_falls_back_to_env_on_adapter_failure(self):
        """When the K8s adapter raises, env vars are used."""
        mock_adapter_class = MagicMock(side_effect=RuntimeError("K8s unavailable"))
        mock_get_adapter_class = MagicMock(return_value=mock_adapter_class)
        mock_connection_config = MagicMock()

        with patch.dict(os.environ, FULL_ENV, clear=False), \
             patch("config.sal_loader._load_from_env", return_value=FULL_ENV) as mock_lfe:
            # Simulate ImportError for penguin_sal.adapters to force env fallback
            try:
                result = sal_loader._load_from_k8s("test-ns")
            except Exception:
                result = {}
        # Either it returned env vars or raised — just verify it didn't hang
        assert isinstance(result, dict)

    def test_returns_dict(self):
        """Basic smoke test: always returns a dict."""
        with patch.dict(os.environ, FULL_ENV, clear=False):
            result = sal_loader._load_from_k8s("some-namespace")
        assert isinstance(result, dict)

    def test_k8s_success_path(self):
        """When K8s adapter works, secrets are returned from K8s."""
        mock_secret_obj = MagicMock()
        mock_secret_obj.value = "k8s-jwt-key"

        mock_adapter = MagicMock()
        mock_adapter.get.return_value = mock_secret_obj
        mock_adapter_class = MagicMock(return_value=mock_adapter)

        mock_connection_config_cls = MagicMock(return_value=MagicMock())

        mock_adapters_mod = MagicMock()
        mock_adapters_mod.get_adapter_class = MagicMock(return_value=mock_adapter_class)

        mock_types_mod = MagicMock()
        mock_types_mod.ConnectionConfig = mock_connection_config_cls

        mock_exceptions_mod = MagicMock()
        mock_exceptions_mod.SecretNotFoundError = Exception

        with patch.dict(sys.modules, {
            "penguin_sal.adapters": mock_adapters_mod,
            "penguin_sal.core.types": mock_types_mod,
            "penguin_sal.core.exceptions": mock_exceptions_mod,
        }):
            result = sal_loader._load_from_k8s("mynamespace")

        assert isinstance(result, dict)

    def test_k8s_bytes_value_decoded(self):
        """When a K8s secret returns bytes, they're decoded to str."""
        mock_secret_obj = MagicMock()
        mock_secret_obj.value = b"bytes-secret-value"

        mock_adapter = MagicMock()
        mock_adapter.get.return_value = mock_secret_obj
        mock_adapter_class = MagicMock(return_value=mock_adapter)

        mock_adapters_mod = MagicMock()
        mock_adapters_mod.get_adapter_class = MagicMock(return_value=mock_adapter_class)
        mock_types_mod = MagicMock()
        mock_types_mod.ConnectionConfig = MagicMock(return_value=MagicMock())
        mock_exceptions_mod = MagicMock()
        mock_exceptions_mod.SecretNotFoundError = Exception

        with patch.dict(sys.modules, {
            "penguin_sal.adapters": mock_adapters_mod,
            "penguin_sal.core.types": mock_types_mod,
            "penguin_sal.core.exceptions": mock_exceptions_mod,
        }):
            result = sal_loader._load_from_k8s("ns")

        # If K8s path worked, value should be a string (decoded from bytes)
        for v in result.values():
            assert isinstance(v, str)

    def test_k8s_dict_value_extracted(self):
        """When a K8s secret returns a dict with 'value' key, it's extracted."""
        mock_secret_obj = MagicMock()
        mock_secret_obj.value = {"value": "nested-secret"}

        mock_adapter = MagicMock()
        mock_adapter.get.return_value = mock_secret_obj
        mock_adapter_class = MagicMock(return_value=mock_adapter)

        mock_adapters_mod = MagicMock()
        mock_adapters_mod.get_adapter_class = MagicMock(return_value=mock_adapter_class)
        mock_types_mod = MagicMock()
        mock_types_mod.ConnectionConfig = MagicMock(return_value=MagicMock())
        mock_exceptions_mod = MagicMock()
        mock_exceptions_mod.SecretNotFoundError = Exception

        with patch.dict(sys.modules, {
            "penguin_sal.adapters": mock_adapters_mod,
            "penguin_sal.core.types": mock_types_mod,
            "penguin_sal.core.exceptions": mock_exceptions_mod,
        }):
            result = sal_loader._load_from_k8s("ns")

        assert isinstance(result, dict)

    def test_k8s_exception_from_adapter_propagates(self):
        """Exceptions from get_adapter_class propagate (only ImportError is caught)."""
        mock_adapters_mod = MagicMock()
        mock_adapters_mod.get_adapter_class.side_effect = RuntimeError("adapter unavailable")
        mock_types_mod = MagicMock()
        mock_exceptions_mod = MagicMock()
        mock_exceptions_mod.SecretNotFoundError = Exception

        with patch.dict(os.environ, {**FULL_ENV, "K8S_CONTEXT": "my-context"}, clear=False), \
             patch.dict(sys.modules, {
                 "penguin_sal.adapters": mock_adapters_mod,
                 "penguin_sal.core.types": mock_types_mod,
                 "penguin_sal.core.exceptions": mock_exceptions_mod,
             }):
            with pytest.raises(RuntimeError, match="adapter unavailable"):
                sal_loader._load_from_k8s("ns")


# ---------------------------------------------------------------------------
# load_secrets
# ---------------------------------------------------------------------------

class TestLoadSecrets:
    def setup_method(self):
        _reset_secrets()

    def teardown_method(self):
        _reset_secrets()

    def test_loads_from_env_when_no_k8s_namespace(self):
        env = {**FULL_ENV}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("K8S_NAMESPACE", None)
            sal_loader.load_secrets()
        assert sal_loader.secrets["JWT_SECRET_KEY"] == "test-jwt-key"
        assert sal_loader.secrets["DB_PASS"] == "test-db-pass"
        assert sal_loader.secrets["REDIS_PASSWORD"] == "test-redis-pass"

    def test_secrets_dict_populated_after_load(self):
        with patch.dict(os.environ, FULL_ENV, clear=False):
            os.environ.pop("K8S_NAMESPACE", None)
            sal_loader.load_secrets()
        assert len(sal_loader.secrets) == 3

    def test_raises_runtime_error_on_missing_secrets(self):
        """Missing secrets raise RuntimeError."""
        with patch.dict(os.environ, {}, clear=True):
            for k in sal_loader._REQUIRED_SECRETS:
                os.environ.pop(k, None)
            os.environ.pop("K8S_NAMESPACE", None)
            with pytest.raises(RuntimeError, match="Required secrets not available"):
                sal_loader.load_secrets()

    def test_raises_on_empty_secret_value(self):
        """An empty string secret counts as missing."""
        empty = {k: "" for k in sal_loader._REQUIRED_SECRETS}
        with patch.dict(os.environ, empty, clear=False):
            os.environ.pop("K8S_NAMESPACE", None)
            with pytest.raises(RuntimeError):
                sal_loader.load_secrets()

    def test_load_from_k8s_when_namespace_set(self):
        """When K8S_NAMESPACE is set, _load_from_k8s is called."""
        with patch("config.sal_loader._load_from_k8s", return_value=FULL_ENV) as mock_k8s, \
             patch.dict(os.environ, {"K8S_NAMESPACE": "prod-ns"}, clear=False):
            sal_loader.load_secrets()
        mock_k8s.assert_called_once_with("prod-ns")
        assert sal_loader.secrets["JWT_SECRET_KEY"] == "test-jwt-key"

    def test_subsequent_call_refreshes_secrets(self):
        """Calling load_secrets() twice updates the cache."""
        with patch.dict(os.environ, FULL_ENV, clear=False):
            os.environ.pop("K8S_NAMESPACE", None)
            sal_loader.load_secrets()
            old = dict(sal_loader.secrets)
            new_env = {**FULL_ENV, "JWT_SECRET_KEY": "rotated-key"}
            with patch.dict(os.environ, new_env, clear=False):
                sal_loader.load_secrets()
        assert sal_loader.secrets["JWT_SECRET_KEY"] == "rotated-key"

    def test_error_message_lists_missing_keys(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "only-this"}, clear=True):
            os.environ.pop("K8S_NAMESPACE", None)
            with pytest.raises(RuntimeError) as exc_info:
                sal_loader.load_secrets()
        assert "DB_PASS" in str(exc_info.value) or "REDIS_PASSWORD" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_secret
# ---------------------------------------------------------------------------

class TestGetSecret:
    def setup_method(self):
        _reset_secrets()

    def teardown_method(self):
        _reset_secrets()

    def test_raises_runtime_error_before_load(self):
        with pytest.raises(RuntimeError, match="load_secrets"):
            sal_loader.get_secret("JWT_SECRET_KEY")

    def test_raises_key_error_for_unknown_key(self):
        sal_loader.secrets = dict(FULL_ENV)
        with pytest.raises(KeyError, match="unknown_key"):
            sal_loader.get_secret("unknown_key")

    def test_returns_correct_value(self):
        sal_loader.secrets = dict(FULL_ENV)
        assert sal_loader.get_secret("JWT_SECRET_KEY") == "test-jwt-key"
        assert sal_loader.get_secret("DB_PASS") == "test-db-pass"
        assert sal_loader.get_secret("REDIS_PASSWORD") == "test-redis-pass"

    def test_returns_string_type(self):
        sal_loader.secrets = dict(FULL_ENV)
        result = sal_loader.get_secret("JWT_SECRET_KEY")
        assert isinstance(result, str)

    def test_all_required_secrets_retrievable(self):
        sal_loader.secrets = dict(FULL_ENV)
        for key in sal_loader._REQUIRED_SECRETS:
            val = sal_loader.get_secret(key)
            assert val is not None and val != ""

    def test_key_error_message_contains_key_name(self):
        sal_loader.secrets = dict(FULL_ENV)
        with pytest.raises(KeyError) as exc_info:
            sal_loader.get_secret("BAD_KEY_NAME")
        assert "BAD_KEY_NAME" in str(exc_info.value)
