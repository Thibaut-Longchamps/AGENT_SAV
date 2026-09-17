# Procédure de rupture de stock

Version : 1.0  
Statut : approuvée

Utiliser cette procédure lorsque la quantité disponible d'un produit est égale à zéro
et que le stock physique est lui-même nul.

1. Vérifier `on_hand_quantity`, `reserved_quantity` et la quantité disponible.
2. Confirmer qu'il s'agit d'une rupture réelle.
3. Ne pas promettre de date de réapprovisionnement sans source métier.
4. Informer le client ou l'opérateur de l'indisponibilité.
5. Escalader si la rupture bloque une commande déjà confirmée.

Le RAG ne modifie jamais le stock.
