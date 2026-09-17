# Classe de base commune à toutes les erreurs métier prévues.
# Elle permet de distinguer les erreurs métier des erreurs techniques.
class DomainError(Exception):
    pass


# Levée lorsqu'une commande demandée n'existe pas.
class OrderNotFoundError(DomainError):
    pass


# Levée lorsqu'un client demandé n'existe pas.
class CustomerNotFoundError(DomainError):
    pass


# Levée lorsqu'une livraison demandée n'existe pas.
class DeliveryNotFoundError(DomainError):
    pass


# Levée lorsqu'un produit demandé n'existe pas.
class ProductNotFoundError(DomainError):
    pass


# Levée lorsqu'une règle métier interdit la création d'un incident.
class IncidentNotAllowedError(DomainError):
    pass


# Levée lorsqu'une même clé d'idempotence est réutilisée
# avec une demande différente.
class IdempotencyConflictError(DomainError):
    pass
