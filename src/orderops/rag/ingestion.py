import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from orderops.rag.security import detect_prompt_injection


def load_approved_documents(
    directory: Path,
    *,
    splitter: RecursiveCharacterTextSplitter | None = None,
) -> tuple[list[Document], list[str], dict[str, list[str]]]:
    """Filter procedures by injection patterns; return documents, IDs and quarantined files."""
    splitter = splitter or RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
    )
    documents: list[Document] = []
    identifiers: list[str] = []
    quarantined: dict[str, list[str]] = {}

    for path in sorted(directory.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        suspicious = detect_prompt_injection(content)
        if suspicious:
            quarantined[path.name] = suspicious
            continue

        for index, chunk in enumerate(splitter.split_text(content)):
            identifier_source = f"{path.name}:v1:{index}:{chunk}"
            identifiers.append(hashlib.sha256(identifier_source.encode()).hexdigest())
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": path.name,
                        "version": "1",
                        "approved": True,
                        "chunk_index": index,
                    },
                )
            )

    return documents, identifiers, quarantined
