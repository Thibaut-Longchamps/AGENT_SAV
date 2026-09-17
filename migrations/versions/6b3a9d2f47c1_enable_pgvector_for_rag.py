"""Enable pgvector for RAG.

Revision ID: 6b3a9d2f47c1
Revises: 17886d3105c6
Create Date: 2026-08-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "6b3a9d2f47c1"
down_revision: str | Sequence[str] | None = "17886d3105c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
