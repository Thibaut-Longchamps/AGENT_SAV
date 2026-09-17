"""create orderops business tables

Revision ID: 17886d3105c6
Revises:
Create Date: 2026-08-22 19:16:29.234704

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "17886d3105c6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Création des tables, contraintes et index métier.
    op.create_table(
        "action_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_audit")),
    )
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_customers")),
        sa.UniqueConstraint("email", name=op.f("uq_customers_email")),
    )
    op.create_table(
        "products",
        sa.Column("product_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_products")),
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_events")),
    )
    op.create_table(
        "inventory",
        sa.Column("product_id", sa.String(length=50), nullable=False),
        sa.Column("on_hand_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("on_hand_quantity >= 0", name=op.f("ck_inventory_on_hand_nonnegative")),
        sa.CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name=op.f("ck_inventory_reserved_not_above_on_hand"),
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0", name=op.f("ck_inventory_reserved_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.product_id"],
            name=op.f("fk_inventory_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_inventory")),
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("expected_delivery", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')",
            name=op.f("ck_orders_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
            name=op.f("fk_orders_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False)
    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.String(length=50), nullable=False),
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("carrier", sa.String(length=100), nullable=True),
        sa.Column("tracking_number", sa.String(length=100), nullable=True),
        sa.Column("expected_delivery", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_transit', 'delayed', 'delivered', 'failed')",
            name=op.f("ck_deliveries_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name=op.f("fk_deliveries_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("delivery_id", name=op.f("pk_deliveries")),
        sa.UniqueConstraint("order_id", name=op.f("uq_deliveries_order_id")),
    )
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'rejected')",
            name=op.f("ck_incidents_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name=op.f("fk_incidents_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("incident_id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_incidents_idempotency_key")),
    )
    op.create_index(op.f("ix_incidents_order_id"), "incidents", ["order_id"], unique=False)
    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("product_id", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_quantity_positive")),
        sa.CheckConstraint("unit_price >= 0", name=op.f("ck_order_items_price_nonnegative")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.product_id"],
            name=op.f("fk_order_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Suppression des objets créés par cette révision.
    op.drop_index(op.f("ix_order_items_product_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_incidents_order_id"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("deliveries")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_table("inventory")
    op.drop_table("security_events")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("action_audit")
