import pytest
from pydantic import ValidationError

from orderops.config import Settings


def test_non_secret_settings_have_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MISTRAL_API_KEY", "LANGSMITH_TRACING", "MCP_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/db",
        checkpoint_database_url="postgresql://user:pass@localhost/db",
    )
    assert settings.mcp_url.endswith("/mcp")
    assert settings.langsmith_tracing is False
    assert settings.mistral_api_key.get_secret_value() == ""


def test_settings_repr_hides_database_credentials_and_api_keys() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:private-db-password@localhost/db",
        checkpoint_database_url="postgresql://user:private-checkpoint-password@localhost/db",
        mistral_api_key="private-mistral-placeholder",
        langsmith_api_key="private-langsmith-placeholder",
        mcp_internal_token="private-mcp-placeholder",
    )
    assert "private-" not in repr(settings)
    assert "private-" not in str(settings)


def test_settings_validation_message_hides_input_values() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            database_url="postgresql://localhost/db",
            checkpoint_database_url="postgresql://localhost/db",
            mcp_port="private-accidental-secret",
        )
    assert "private-accidental-secret" not in str(error.value)
