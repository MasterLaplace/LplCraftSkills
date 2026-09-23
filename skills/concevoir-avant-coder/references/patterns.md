# Catalogue court de design patterns : problème, signal, coût

**À lire quand on hésite entre deux formes, jamais pour choisir un pattern à l'avance.** Un pattern est le
nom d'une forme qu'on constate ; partir du nom produit le nom, partir du problème produit la solution.

Chaque entrée répond à trois questions : **quel problème**, **quel signal dit qu'on y est**, **ce que ça
coûte**. La dernière colonne est celle qu'on oublie, et c'est celle qui décide.

## Création

| Pattern | Le problème | Le signal | Le coût |
|---|---|---|---|
| **Fabrique** (Factory) | choisir une implémentation selon une entrée | un aiguillage sur un type, qui construit | une indirection ; inutile s'il n'y a qu'un cas |
| **Monteur** (Builder) | un objet à beaucoup de paramètres optionnels, invalide à mi-construction | un constructeur à sept paramètres, ou un objet mutable qu'on remplit | du code à maintenir en double du modèle |
| **Singleton** | *presque toujours le mauvais choix* | on veut « une seule instance » | **état global** : tests couplés, ordre d'initialisation fragile, concurrence. Préférer une instance unique **injectée** |
| **Réserve d'objets** (Object pool) | l'allocation domine le coût, jeux, embarqué, temps réel | un profileur, pas une intuition | complexité de cycle de vie et de remise à zéro ; ne jamais faire sans mesure |

## Structure

| Pattern | Le problème | Le signal | Le coût |
|---|---|---|---|
| **Adaptateur** (Adapter) | deux contrats incompatibles qu'on ne contrôle pas | du code de conversion recopié à plusieurs endroits | une couche de plus ; excellente frontière pour isoler une bibliothèque tierce |
| **Façade** (Facade) | un sous-système large dont les appelants n'utilisent qu'un chemin | tous les appelants font la même séquence de cinq appels | risque de devenir un objet fourre-tout si elle grossit |
| **Décorateur** (Decorator) | ajouter un comportement sans modifier ni sous-classer | on veut cumuler des variantes : cache, journal, réessai | une pile difficile à suivre au débogueur ; l'ordre devient significatif |
| **Mandataire** (Proxy) | contrôler l'accès : paresse, cache, droits, distance | l'appelant ne doit pas savoir que c'est cher ou distant | cacher un coût réseau derrière un appel banal induit en erreur |
| **Composite** | traiter un élément et un groupe uniformément | des tests « est-ce une feuille » partout | les opérations qui n'ont pas de sens sur une feuille, ou l'inverse |

## Comportement

| Pattern | Le problème | Le signal | Le coût |
|---|---|---|---|
| **Stratégie** (Strategy) | un algorithme varie, le reste non | un aiguillage sur un mode, répété à plusieurs endroits | une interface plus N classes ; ne se justifie qu'à partir de deux cas **réels** |
| **État** (State) | le comportement dépend d'un état, et les transitions sont des règles | des booléens qui se combinent (`estBrouillon && !estVerrouille`) | plus verbeux ; rentable quand les transitions illégales doivent devenir impossibles |
| **Observateur**, publication-abonnement | plusieurs réactions à un événement, sans que l'émetteur les connaisse | l'émetteur importe ses consommateurs | **le flux devient invisible** : plus de pile d'appels lisible, ordre non garanti, fuites d'abonnement |
| **Commande** (Command) | réifier une action : file d'attente, annulation, rejeu, journal | on veut « annuler » ou « rejouer » | une classe par action ; excellent quand l'historique est le besoin |
| **Patron de méthode** (Template Method) | un squelette fixe, des trous variables | de l'héritage pour partager une séquence | **couple par l'héritage** ; en composition, c'est Stratégie, la préférer |
| **Chaîne de responsabilité** | plusieurs traitants possibles, le premier qui sait répond | des cascades de conditions de répartition qui grossissent | qui a traité devient dur à savoir : **journaliser le maillon retenu** |
| **Visiteur** (Visitor) | ajouter des opérations sur une hiérarchie stable | on ajoute souvent des opérations, rarement des types | **inverse la facilité** : ajouter un type devient coûteux. Faux ami si la hiérarchie bouge |

## Concurrence et frontières

| Pattern | Le problème | Le signal | Le coût |
|---|---|---|---|
| **Producteur / consommateur** | découpler un rythme d'un autre | un appelant lent bloque un producteur rapide | la file **doit être bornée**, et la politique de saturation choisie explicitement |
| **Disjoncteur** (Circuit breaker) | arrêter de marteler une dépendance en panne | des rafales d'expirations en cascade | des seuils à régler ; **inutile sans mesure de ce qu'il coupe** |
| **Port et adaptateur** (hexagonal) | le métier ne doit dépendre ni de la base ni du transport | pour tester une règle, il faut une base de données | des interfaces en plus ; rentable dès que le métier a une vraie valeur à protéger |
| **Agrégat** (Aggregate) | plusieurs objets doivent rester cohérents ensemble, et n'importe quel appelant peut les modifier séparément | on fabrique un enfant à côté de son parent, en espérant que l'ensemble reste valide | une seule porte en écriture, donc des jointures explicites en lecture ; trop gros, il devient lent à charger et disputé entre appelants |
| **Lecture et écriture séparées** (CQRS) | la forme qui garantit l'invariant n'est pas celle que l'affichage réclame | on charge un graphe d'objets entier pour afficher trois colonnes | deux modèles à tenir en phase ; inutile tant que la forme qui garantit l'invariant est celle qu'on affiche |
| **Boîte d'envoi transactionnelle** (Outbox) | un effet externe doit suivre une écriture, sans la faire échouer ni se perdre quand elle réussit | un envoi juste après la validation, sous un `catch` qui avale l'erreur | une table, un lecteur, un délai ; et le consommateur **doit** être idempotent dès qu'une reprise existe |

## Les trois pièges qui reviennent

1. **Le pattern posé d'avance.** Une fabrique écrite pour un seul cas est une indirection pure. La forme
   doit *émerger* du deuxième cas.
2. **Le pattern qui cache un coût.** Mandataire et décorateur rendent invisible ce qui est cher, un aller
   réseau derrière un appel qui a l'air local. Si le coût compte, il doit rester lisible **au site
   d'appel**.
3. **Le pattern comme argument d'autorité en revue.** « C'est le pattern X » ne répond pas à *quel problème
   réel résout-il ici*. Si la réponse n'existe pas, le pattern est du coût sans contrepartie.

## La question qui remplace tout ce catalogue

> **Qu'est-ce qui varie, et à quelle fréquence ?**

Ce qui varie souvent doit être isolé derrière un contrat ; ce qui ne varie pas doit rester en ligne, simple
et lisible. La plupart des patterns ci-dessus ne sont que des réponses différentes à cette même question, et
quand on y a répondu, le nom du pattern devient un détail de vocabulaire.
