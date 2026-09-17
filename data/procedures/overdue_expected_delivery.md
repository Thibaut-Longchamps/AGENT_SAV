# Procédure de date de livraison prévue dépassée

Version : 1.0  
Statut : approuvée

Utiliser cette procédure lorsque `expected_delivery` est antérieure à la date courante
et que la commande n'est pas `delivered`.

1. Vérifier le statut de commande.
2. Vérifier la présence éventuelle d'une livraison et son statut.
3. Déterminer si le problème relève d'un retard transporteur, d'une commande non expédiée
   ou d'un tracking manquant.
4. Appliquer la procédure spécialisée correspondante.
5. Si aucune explication fiable n'existe, proposer une escalade ou un incident après
   validation humaine.

Ne jamais déduire qu'un colis est perdu uniquement à partir de la date dépassée.
