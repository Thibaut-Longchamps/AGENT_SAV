# Modèles ORM des tables métier : colonnes, clés, contraintes et relations.
# Alembic compare ces métadonnées au schéma PostgreSQL pour générer les migrations.

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orderops.db.base import Base


class RoleRow(Base):
    __tablename__ = "roles"
    role_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class UserRow(Base):
    __tablename__ = "users"
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class UserRoleRow(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_roles_single_role"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), primary_key=True)


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'approval_required', 'error')",
            name="conversation_status_valid",
        ),
    )
    thread_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'completed'"), index=True
    )
    pending_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ============================================================
# CLIENTS
# ============================================================


class CustomerRow(Base):
    """Représentation ORM de la table PostgreSQL customers."""

    __tablename__ = "customers"

    # Identifiant métier du client = clé primaire.
    customer_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Deux clients ne peuvent pas avoir le même email.
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
    )

    # Champ facultatif : NULL autorisé en base.
    phone: Mapped[str | None] = mapped_column(
        String(50),
    )

    # PostgreSQL renseigne automatiquement la date de création.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# PRODUITS
# ============================================================


class ProductRow(Base):
    """Table contenant les produits disponibles dans OrderOps."""

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )


# ============================================================
# STOCK
# ============================================================


class InventoryRow(Base):
    """Quantités physiques et réservées pour chaque produit."""

    __tablename__ = "inventory"

    # Contraintes directement garanties par PostgreSQL.
    __table_args__ = (
        CheckConstraint(
            "on_hand_quantity >= 0",
            name="on_hand_nonnegative",
        ),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="reserved_nonnegative",
        ),
        CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name="reserved_not_above_on_hand",
        ),
    )

    # La clé primaire limite le stock à une ligne par produit.
    # La clé étrangère impose l'existence du produit associé.
    product_id: Mapped[str] = mapped_column(
        ForeignKey(
            "products.product_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )

    on_hand_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# COMMANDES
# ============================================================


class OrderRow(Base):
    """Commande enregistrée dans PostgreSQL."""

    __tablename__ = "orders"

    # PostgreSQL refuse tout statut qui n'appartient pas à cette liste.
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')",
            name="valid_status",
        ),
    )

    order_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    # Une commande appartient obligatoirement à un client existant.
    customer_id: Mapped[str] = mapped_column(
        ForeignKey(
            "customers.customer_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )

    expected_delivery: Mapped[date | None] = mapped_column(
        Date,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relation Python entre une commande et ses lignes de commande.
    #
    # lazy="raise" refuse l'accès aux lignes qui n'ont pas été chargées.
    # Le repository les charge explicitement avec selectinload.
    items: Mapped[list[OrderItemRow]] = relationship(
        back_populates="order",
        lazy="raise",
    )


# ============================================================
# LIGNES DE COMMANDE
# ============================================================


class OrderItemRow(Base):
    """Produit et quantité contenus dans une commande."""

    __tablename__ = "order_items"

    __table_args__ = (
        # Un même produit ne peut apparaître qu'une fois
        # dans une même commande.
        UniqueConstraint(
            "order_id",
            "product_id",
            name="uq_order_items_order_product",
        ),
        CheckConstraint(
            "quantity > 0",
            name="quantity_positive",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="price_nonnegative",
        ),
    )

    # Identity() demande à PostgreSQL de générer automatiquement l'identifiant.
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    # Si une commande est supprimée, ses lignes sont également supprimées.
    order_id: Mapped[str] = mapped_column(
        ForeignKey(
            "orders.order_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey(
            "products.product_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Montant décimal sur douze chiffres, dont deux après la virgule.
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # Relation inverse de OrderRow.items.
    order: Mapped[OrderRow] = relationship(
        back_populates="items",
        lazy="raise",
    )


# ============================================================
# LIVRAISONS
# ============================================================


class DeliveryRow(Base):
    """Informations de livraison associées à une commande."""

    __tablename__ = "deliveries"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_transit', 'delayed', 'delivered', 'failed')",
            name="valid_status",
        ),
    )

    delivery_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    # unique=True signifie qu'une commande
    # ne peut avoir qu'une seule livraison dans ce MVP.
    order_id: Mapped[str] = mapped_column(
        ForeignKey(
            "orders.order_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    carrier: Mapped[str | None] = mapped_column(
        String(100),
    )

    tracking_number: Mapped[str | None] = mapped_column(
        String(100),
    )

    expected_delivery: Mapped[date | None] = mapped_column(
        Date,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# INCIDENTS SAV
# ============================================================


class IncidentRow(Base):
    """Incident associé à une commande, avec son statut et sa clé d'idempotence."""

    __tablename__ = "incidents"

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'rejected')",
            name="valid_status",
        ),
    )

    incident_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    order_id: Mapped[str] = mapped_column(
        ForeignKey(
            "orders.order_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'open'"),
    )

    # Clé unique utilisée pour empêcher la création
    # accidentelle du même incident plusieurs fois.
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    # Empreinte SHA-256 du contenu métier de la demande.
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# AUDIT DES ACTIONS
# ============================================================


class ActionAuditRow(Base):
    """Journal des actions métier, de leurs auteurs et de leurs résultats."""

    __tablename__ = "action_audit"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    # Exemple : "create_incident".
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Exemple : "incident" ou "order".
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Identifiant de l'acteur ; le tool de création transmet celui du superviseur.
    actor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # La création d'incident produit "created" ou "already_existed".
    outcome: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # JSONB permet de stocker des informations supplémentaires
    # structurées sans créer une colonne pour chaque détail.
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ============================================================
# ÉVÉNEMENTS DE SÉCURITÉ
# ============================================================


class SecurityEventRow(Base):
    """Événements liés à la sécurité de l'application."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    # Exemple : "prompt_injection_detected".
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Origine de l'événement : document, requête, utilisateur...
    source: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
