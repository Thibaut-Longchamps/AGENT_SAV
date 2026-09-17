# Procédure de création d'un incident

Version : 1.0  
Statut : approuvée

Créer un incident lorsqu'un problème SAV nécessite un suivi persistant : retard confirmé,
livraison en échec, absence prolongée de suivi, produit endommagé ou autre anomalie validée.

1. Vérifier la commande.
2. Vérifier le problème avec les tools métier.
3. Vérifier qu'un incident équivalent n'existe pas déjà si l'information est disponible.
4. Préparer un motif factuel et une clé d'idempotence stable.
5. Demander explicitement la validation humaine.
6. Seulement après validation, appeler `create_incident`.

Ne jamais affirmer qu'un incident a été créé avant le résultat réel du tool.
