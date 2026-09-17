# Procédure de stock entièrement réservé

Version : 1.0  
Statut : approuvée

Utiliser cette procédure lorsque `on_hand_quantity` est supérieur à zéro mais que
`reserved_quantity` est égal au stock physique, donc quantité disponible égale à zéro.

1. Distinguer ce cas d'une rupture physique.
2. Vérifier les quantités réellement disponibles.
3. Informer que le stock existe mais n'est actuellement pas disponible.
4. Ne pas libérer ou déplacer une réservation automatiquement.
5. Escalader à un opérateur si une commande est bloquée.

Ne jamais présenter un stock réservé comme immédiatement disponible.
