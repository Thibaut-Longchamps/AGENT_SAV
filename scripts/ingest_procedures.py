import asyncio
from pathlib import Path

from orderops.rag.ingestion import load_approved_documents
from orderops.rag.store import build_vector_store


async def main() -> None:
    engine, store = build_vector_store()
    documents, identifiers, quarantined = load_approved_documents(Path("data/procedures"))
    try:
        for filename, patterns in quarantined.items():
            print(f"QUARANTINE {filename}: patterns={patterns}")
        if documents:
            await store.aadd_documents(documents=documents, ids=identifiers)
        print(f"{len(documents)} chunks ingérés")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
