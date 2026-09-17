from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# BaseSettings lit les variables du processus et le fichier .env.
# SecretStr masque les clés dans les représentations textuelles des champs.


# Configuration de l'application.
class Settings(BaseSettings):
    # Charge les variables depuis .env.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Environnement de l'application.
    app_env: str = "development"

    # Les URL PostgreSQL sont exclues du repr car elles peuvent contenir un mot de passe.
    database_url: str = Field(repr=False)
    checkpoint_database_url: str = Field(repr=False)

    # Serveur MCP.
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001
    mcp_url: str = "http://127.0.0.1:8001/mcp"
    # Valeur publique réservée à la démonstration locale, sans authentification.
    mcp_internal_token: SecretStr = SecretStr("orderops-local-demo-only")
    demo_mode: bool = True

    # Mistral.
    mistral_api_key: SecretStr = SecretStr("")
    mistral_chat_model: str = "mistral-small-latest"
    mistral_embed_model: str = "mistral-embed"

    # LangSmith.
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_project: str = "orderops-ai-agent"

    # Endpoint utilisé en l'absence de LANGSMITH_ENDPOINT dans l'environnement et .env.
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # URL FastAPI utilisée notamment par l'interface Streamlit.
    orderops_api_url: str = "http://127.0.0.1:8000"


@lru_cache
def get_settings() -> Settings:
    # Le cache conserve l'instance jusqu'à cache_clear() ou l'arrêt du processus.
    return Settings()  # type: ignore[call-arg]
