"""Add demo users, roles and durable conversation metadata.

Revision ID: 927fc453bb12
Revises: 6b3a9d2f47c1
"""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "927fc453bb12"
down_revision = "6b3a9d2f47c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("role_id", sa.String(30), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
    )
    users = op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    user_roles = op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column("role_id", sa.String(30), sa.ForeignKey("roles.role_id"), primary_key=True),
        sa.UniqueConstraint("user_id", name="uq_user_roles_single_role"),
    )
    op.create_table(
        "conversations",
        sa.Column("thread_id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.user_id")),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'completed'")),
        sa.Column(
            "pending_actions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'approval_required', 'error')",
            name="conversation_status_valid",
        ),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.bulk_insert(
        roles,
        [
            {"role_id": "reader", "label": "Lecteur"},
            {"role_id": "operator", "label": "Opérateur SAV"},
            {"role_id": "supervisor", "label": "Superviseur"},
        ],
    )
    identities = [
        (UUID("00000000-0000-0000-0000-000000000001"), "Camille — Lecteur", "reader"),
        (UUID("00000000-0000-0000-0000-000000000002"), "Alex — Opérateur SAV", "operator"),
        (UUID("00000000-0000-0000-0000-000000000003"), "Sam — Superviseur", "supervisor"),
    ]
    op.bulk_insert(
        users, [{"user_id": key, "name": name, "active": True} for key, name, _role in identities]
    )
    op.bulk_insert(
        user_roles, [{"user_id": key, "role_id": role} for key, _name, role in identities]
    )


def downgrade() -> None:
    op.drop_table("conversations")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
