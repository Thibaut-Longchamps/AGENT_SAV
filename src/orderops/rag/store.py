from langchain_mistralai import MistralAIEmbeddings
from langchain_postgres import PGVector
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from orderops.config import Settings, get_settings


def build_vector_store(settings: Settings | None = None) -> tuple[AsyncEngine, PGVector]:
    settings = settings or get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    embeddings = MistralAIEmbeddings(
        model=settings.mistral_embed_model,
        api_key=settings.mistral_api_key,
    )
    store = PGVector(
        embeddings=embeddings,
        collection_name="orderops_procedures_v1",
        connection=engine,
        embedding_length=1024,
        use_jsonb=True,
        create_extension=False,
    )
    return engine, store
