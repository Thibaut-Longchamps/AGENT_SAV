import hashlib  # Calcule une empreinte SHA-256.
import json  # Sérialise les données en JSON.
from datetime import date, datetime  # date = jour ; datetime = date + heure.
from decimal import Decimal  # Nombre décimal précis, adapté aux prix.

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orderops.domain.enums import DeliveryStatus, IncidentStatus, OrderStatus


# Modèle de base de tous les objets métier.
class DomainModel(BaseModel):
    model_config = ConfigDict(
        frozen=True  # Rend les objets immuables après création.
    )


# Client.
class Customer(DomainModel):
    customer_id: str
    name: str
    email: str
    phone: str | None = None  # Optionnel.


# Produit contenu dans une commande.
class OrderItem(DomainModel):
    product_id: str
    product_name: str

    quantity: int = Field(gt=0)
    # gt=0 : strictement supérieur à 0.

    unit_price: Decimal = Field(ge=0)
    # ge=0 : supérieur ou égal à 0.


# Commande.
class Order(DomainModel):
    order_id: str
    customer_id: str
    status: OrderStatus  # Valeur imposée par l'enum OrderStatus.
    created_at: datetime
    expected_delivery: date | None = None

    items: tuple[OrderItem, ...] = ()
    # Tuple contenant zéro ou plusieurs OrderItem.


# Livraison.
class Delivery(DomainModel):
    delivery_id: str
    order_id: str
    status: DeliveryStatus
    carrier: str | None = None
    tracking_number: str | None = None
    expected_delivery: date | None = None


# Stock d'un produit.
class ProductStock(DomainModel):
    product_id: str
    product_name: str

    on_hand_quantity: int = Field(ge=0)  # Stock physique.
    reserved_quantity: int = Field(ge=0)  # Stock déjà réservé.
    quantity_available: int = Field(ge=0)  # Stock réellement disponible.


# Incident existant.
class Incident(DomainModel):
    incident_id: str
    order_id: str
    reason: str
    status: IncidentStatus

    idempotency_key: str
    # Clé utilisée pour éviter de créer plusieurs fois la même opération.

    created_at: datetime


# Demande de création d'un incident.
class CreateIncidentCommand(DomainModel):
    order_id: str = Field(min_length=3, max_length=50)
    reason: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)
    # min_length / max_length : longueurs autorisées pour chaque chaîne.

    # field_validator indique à Pydantic d'exécuter automatiquement
    # cette méthode lors de la validation des champs indiqués.
    @field_validator("order_id", "idempotency_key")
    # classmethod signifie que la méthode est liée à la classe
    # et reçoit cls au lieu d'une instance self.
    # C'est la forme utilisée par Pydantic pour les validateurs de champs.
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        # value contient la valeur du champ en cours de validation.
        # Retire les espaces au début et à la fin.
        return value.strip()

    # Ce validateur s'applique uniquement au champ reason.
    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        # Transforme "Retard   confirmé" en "Retard confirmé".
        return " ".join(value.split())

    def request_hash(self) -> str:
        # Données métier utilisées pour identifier la demande.
        payload = {
            "order_id": self.order_id,
            "reason": self.reason,
        }

        # Produit une représentation JSON stable.
        canonical = json.dumps(
            payload,
            sort_keys=True,  # Trie les clés.
            ensure_ascii=False,  # Conserve les caractères accentués.
            separators=(",", ":"),  # Supprime les espaces inutiles.
        )

        # Encode en UTF-8, calcule SHA-256 et retourne 64 caractères hexadécimaux.
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Résultat d'une tentative de création d'incident.
class IncidentCreationResult(DomainModel):
    incident: Incident

    already_existed: bool
    # False = nouvel incident.
    # True = incident déjà existant.
