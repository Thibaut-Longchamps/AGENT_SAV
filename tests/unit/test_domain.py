from decimal import Decimal

import pytest
from pydantic import ValidationError

from orderops.domain.models import (
    CreateIncidentCommand,
    Customer,
    OrderItem,
    ProductStock,
)


# Vérifie qu'un article avec une quantité égale à 0 est refusé.
# Dans OrderItem, quantity doit être strictement supérieure à 0.
def test_order_item_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError):
        OrderItem(
            product_id="SKU-12",
            product_name="Scanner mobile",
            quantity=0,
            unit_price=Decimal("249.90"),
        )


# Vérifie qu'un stock négatif est refusé.
# on_hand_quantity doit être supérieur ou égal à 0.
def test_product_stock_rejects_negative_quantity() -> None:
    with pytest.raises(ValidationError):
        ProductStock(
            product_id="SKU-12",
            product_name="Scanner mobile",
            on_hand_quantity=-1,
            reserved_quantity=0,
            quantity_available=0,
        )


# Vérifie que CreateIncidentCommand nettoie automatiquement
# les espaces autour des identifiants et les espaces multiples dans reason.
def test_command_normalizes_values() -> None:
    command = CreateIncidentCommand(
        order_id=" CMD-1042 ",
        reason="Retard   confirmé par le transporteur",
        idempotency_key=" notebook-CMD-1042 ",
    )

    assert command.order_id == "CMD-1042"
    assert command.reason == "Retard confirmé par le transporteur"
    assert command.idempotency_key == "notebook-CMD-1042"


# Vérifie que deux demandes ayant le même contenu métier
# produisent exactement le même hash.
# La clé d'idempotence est exclue du hash.
def test_same_payload_produces_same_hash() -> None:
    first = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Livraison en retard",
        idempotency_key="first-key",
    )

    second = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Livraison en retard",
        idempotency_key="second-key",
    )

    assert first.request_hash() == second.request_hash()

    # SHA-256 produit un hash hexadécimal de 64 caractères.
    assert len(first.request_hash()) == 64


# Vérifie qu'une modification du contenu métier
# produit un hash différent.
def test_different_payload_produces_different_hash() -> None:
    first = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Livraison en retard",
        idempotency_key="same-key",
    )

    second = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Colis perdu",
        idempotency_key="same-key",
    )

    assert first.request_hash() != second.request_hash()


# Vérifie que Pydantic refuse une commande
# qui ne respecte pas les contraintes de longueur définies dans le modèle.
def test_invalid_command_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateIncidentCommand(
            order_id="X",
            reason="non",
            idempotency_key="courte",
        )


# Vérifie que les objets du domaine sont immuables.
# DomainModel utilise ConfigDict(frozen=True),
# donc une propriété ne peut pas être modifiée après création.
def test_domain_model_is_immutable() -> None:
    customer = Customer(
        customer_id="CUS-001",
        name="ACME",
        email="sav@acme.example",
    )

    with pytest.raises(ValidationError):
        customer.name = "Autre nom"
