# Les grilles, traduites pour le logiciel

Ce fichier ne se lit pas d'affilée. On y vient avec un sujet, on prend **deux grilles d'axes
différents**, et on garde les questions dont la réponse change quelque chose. Une grille remplie case
par case sans que rien ne change a été récitée, pas utilisée.

## QQOQCCP : le périmètre, en premier

La plus ancienne et la moins chère. Elle descend des « circonstances » de la rhétorique antique, et
Kipling en a fait ses six serviteurs (*what, why, when, how, where, who*).

| Question | Sur un changement ou un incident |
|---|---|
| **Qui** | qui le demande, qui le constate, qui est touché, qui l'exploite, qui sera réveillé la nuit ? |
| **Quoi** | quel comportement observable, exactement ? Qu'est-ce qui n'en fait PAS partie ? |
| **Où** | quel module, quel environnement, quel client, quelle région, quelle version ? |
| **Quand** | depuis quand, à quelle fréquence, à quel moment du cycle (démarrage, pic, fin de mois) ? |
| **Comment** | comment ça se manifeste, comment on le reproduit, comment on saura que c'est réglé ? |
| **Combien** | combien d'utilisateurs, de requêtes, d'euros, de millisecondes ? Mesuré ou estimé ? |
| **Pourquoi** | pourquoi maintenant, pourquoi ce besoin, pourquoi cette solution plutôt qu'une autre ? |

## Les 6M d'Ishikawa : les familles de causes

Le diagramme en arête de poisson range les causes possibles d'un effet en familles. Son intérêt est de
forcer une question par famille, surtout celles qu'on n'aurait pas regardées. Ishikawa n'a jamais figé
de liste : la tradition française part de 5M et ajoute la mesure pour en faire 6, parfois le
management et les moyens pour en faire 8.

| Famille | Traduite en logiciel | Question type |
|---|---|---|
| **Méthode** | l'algorithme, le processus, la procédure de déploiement | la façon de faire est-elle en cause, ou son exécution ? |
| **Matière** | les données d'entrée, les fichiers, les messages reçus | une donnée nouvelle, mal formée, plus grosse, dans un autre encodage ? |
| **Machine** | le matériel, l'infrastructure, le runtime, les dépendances | une version montée, un nœud différent, une ressource saturée ? |
| **Main-d'œuvre** | les humains : utilisateurs, opérateurs, équipes | un usage imprévu, une manipulation, un changement d'équipe ? |
| **Milieu** | l'environnement : configuration, réseau, horloge, fuseau, charge, autres systèmes | qu'est-ce qui diffère entre là où ça marche et là où ça casse ? |
| **Mesure** | l'instrumentation elle-même | **et si c'était la mesure qui mentait**, pas le système ? |

La dernière famille est celle qu'on oublie, et elle rattrape les pièges de mesure : un compteur qui ne
voit pas tout, un filtre écrit de mémoire, un harnais qui perd une ligne.

## SFDIPOT : les dimensions d'un système

Tiré du *Heuristic Test Strategy Model* de James Bach, pour balayer un produit avant de le tester, de
l'auditer ou de le modifier.

| Dimension | Ce qu'on regarde | Question type |
|---|---|---|
| **Structure** | ce dont le produit est fait : code, fichiers, dépendances, schémas | qu'est-ce qui est livré, et qu'est-ce qui ne l'est pas ? |
| **Fonction** | ce qu'il fait | quelles fonctions, y compris celles que personne n'a documentées ? |
| **Données** | ce qu'il traite | quelles entrées, sorties, états persistés, valeurs limites, volumes ? |
| **Interfaces** | par où on lui parle | API, interface, fichiers, messages, CLI : lesquelles, avec quels contrats ? |
| **Plateforme** | ce dont il dépend | système, navigateur, runtime, services externes, versions ? |
| **Opérations** | comment il est utilisé et exploité | qui l'utilise, à quelle fréquence, comment il se déploie, se surveille, se restaure ? |
| **Temps** | ce qui dépend de l'instant | concurrence, délais, fuseaux, changements d'heure, expirations, ordre des événements ? |

## Les mots-guides HAZOP : les déviations

L'industrie des procédés (norme IEC 61882) applique des mots-guides à chaque paramètre d'un système pour
trouver les déviations dangereuses. Appliqués à une entrée, un message ou une étape, ils trouvent les
cas limites plus sûrement que l'imagination.

| Mot-guide | Déviation d'une entrée, d'un message, d'une étape | Exemple de question |
|---|---|---|
| **pas / aucun** | absent, vide, nul, jamais reçu | que se passe-t-il si le message n'arrive jamais ? |
| **plus** | trop grand, trop nombreux, trop souvent | et avec dix mille éléments, ou dix appels par seconde ? |
| **moins** | trop petit, trop peu, tronqué | et si la réponse est tronquée au milieu ? |
| **en plus de** | reçu en double, avec des champs inattendus | et si le même événement arrive deux fois ? |
| **en partie** | incomplet, à moitié écrit | et si le processus meurt entre les deux écritures ? |
| **inverse** | dans l'autre sens, annulé, négatif | et si l'utilisateur annule pendant le traitement ? |
| **autre que** | d'un autre type, d'une autre source, d'un autre encodage | et si le fichier est en UTF-16, ou vient d'un autre client ? |
| **tôt / tard** | avant d'être attendu, après expiration | et si la réponse arrive après le délai d'attente ? |
| **avant / après** | dans le mauvais ordre | et si la mise à jour arrive avant la création ? |

## ZOMBIES : les cas d'un comportement

La mnémonique de James Grenning pour écrire les tests d'une fonction dans un ordre qui fait émerger le
code (voir `tests-first`).

| Lettre | Le cas |
|---|---|
| **Z**éro | l'entrée vide, la collection vide, le premier appel |
| **O**ne (un) | un seul élément |
| **M**any (plusieurs) | plusieurs éléments, et l'ordre compte-t-il ? |
| **B**oundaries (bornes) | les limites : maximum, minimum, juste avant, juste après |
| **I**nterface | la signature : est-elle claire, et que promet-elle ? |
| **E**xceptions | les erreurs, les refus, les entrées invalides |
| **S**imple | commencer par les scénarios simples, et garder les solutions simples |

## STRIDE : les menaces

Pour chaque frontière de confiance (une entrée utilisateur, une API, un fichier reçu, un message d'un
autre service).

| Menace | La propriété violée | Question type |
|---|---|---|
| **S**poofing (usurpation) | authentification | quelqu'un peut-il se faire passer pour un autre ? |
| **T**ampering (altération) | intégrité | une donnée peut-elle être modifiée en route ou au repos ? |
| **R**epudiation | traçabilité | peut-on prouver qui a fait quoi ? |
| **I**nformation disclosure (fuite) | confidentialité | qu'est-ce qui sort dans un journal, une erreur, une réponse ? |
| **D**enial of service | disponibilité | une entrée peut-elle épuiser une ressource ? |
| **E**levation of privilege | autorisation | peut-on obtenir des droits qu'on n'a pas ? |

## Les six familles de questions socratiques

La classification de Richard Paul, utile quand on challenge une affirmation, la sienne ou celle d'un
autre, plutôt qu'un système.

| Famille | Questions |
|---|---|
| **clarifier** | que veux-tu dire exactement par X ? Peux-tu donner un exemple ? |
| **les hypothèses** | qu'est-ce qu'on suppose ici ? Est-ce toujours vrai ? |
| **les preuves** | comment le sait-on ? Qu'est-ce qui le montre ? Est-ce mesuré ? |
| **les points de vue** | comment le verrait l'exploitation, le client, l'équipe voisine ? |
| **les conséquences** | si c'est vrai, qu'est-ce que ça implique ? Et ensuite ? |
| **la question elle-même** | est-ce la bonne question ? Pourquoi celle-là ? |

## Le pré-mortem, en cinq étapes

Le protocole de Gary Klein, à faire **avant** de s'engager, quand le plan est connu mais pas encore
exécuté.

1. **poser le décor** : « nous sommes dans six mois, le projet a échoué, et c'est un échec net » ;
2. **écrire seul, en silence**, pendant quelques minutes, toutes les raisons possibles de cet échec.
   Seul, parce qu'en groupe la première idée dite oriente toutes les autres ;
3. **faire le tour**, une raison par personne à la fois, jusqu'à épuisement, sans débattre ;
4. **trier** : les raisons plausibles et coûteuses d'abord ;
5. **modifier le plan** pour chacune de celles-là, ou écrire pourquoi on accepte le risque.

Seul, le même protocole marche en une page : on écrit l'échec comme déjà arrivé, puis ses causes.

## Le relecteur hostile, avant la vraie revue

1. **écrire les dix questions** que le relecteur le plus exigeant posera. Les plus dérangeantes d'abord ;
2. pour chacune, **la formuler sous sa forme la plus forte** : si on peut la rejeter trop facilement,
   c'est qu'on l'a affaiblie ;
3. **y répondre par un fait**, avec sa source, ou **écrire qu'on ne sait pas** ;
4. **faire jouer le rôle par quelqu'un d'autre**, qui n'a pas écrit le document : un collègue, ou un
   sous-agent sans le contexte de la conversation, chargé de réfuter et de rouvrir chaque source citée.

## Répondre à un point de revue ou d'audit

La même grille pour chaque point, dans le même ordre : c'est ce qui rend les verdicts comparables, et
ce qui empêche de sauter la case qui dérange.

```markdown
### <numero> . <le point en quelques mots>. <le verdict en un mot : juste, faux, partiel, pas maintenant>

La revue dit : <l'affirmation, citee ou resumee fidelement>

La meilleure version de l'argument : <la forme la plus forte, meme si la revue ne l'a pas ecrite>

Ce que j'ai verifie : <la preuve, avec sa commande ou son fichier:ligne ; mesure plutot que deduit>

Ce qui lui manque : <l'hypothese porteuse non verifiee, le cas oublie, le correctif qui casse autre chose>

Ce qui me ferait changer d'avis : <l'observation precise qui inverserait le verdict>

Ma decision : <ce qu'on fait, ou la question a poser et a qui>
```

Avant de rendre, deux passes transverses : **les correctifs retenus se contredisent-ils entre eux ?**
Et **ai-je appliqué la même exigence à mes propres conclusions** qu'aux points du relecteur ?

## Les questions d'une revue de conception

Celles qui reviennent d'une revue à l'autre, et qu'il vaut mieux avoir posées soi-même. Les documents
de conception de Google les figent en sections (contexte, objectifs **et non-objectifs**, alternatives
envisagées, sujets transverses comme la sécurité et l'observabilité), et la liste de contrôle de mise en
production du livre SRE de Google (annexe E) porte les axes charge, bascule et dépendances. Chez Amazon,
la FAQ interne d'un document *Working Backwards* s'écrit avant toute construction, pour répondre d'avance
aux questions de la direction.

| Axe | Questions |
|---|---|
| **le besoin** | quel problème, pour qui, et comment saura-t-on qu'il est résolu ? Qu'est-ce qui n'est **pas** un objectif ? Quelles alternatives ont été écartées, et pourquoi ? |
| **les pannes** | que se passe-t-il quand chaque dépendance est lente, absente, ou répond n'importe quoi ? |
| **l'échelle** | et à dix fois la charge, ou dix fois les données ? Qu'est-ce qui casse en premier ? |
| **le retour arrière** | comment on annule ? Les données écrites entre-temps survivent-elles au retour arrière ? |
| **la compatibilité** | qui dépend de l'ancien contrat ? Les anciens clients, les anciennes données, les anciens messages en file ? |
| **l'observation** | comment saura-t-on que ça marche en production ? Quelle métrique, quelle alerte ? |
| **la sécurité** | quelles frontières de confiance sont traversées ? (voir STRIDE, puis `garder-les-frontieres`) |
| **l'exploitation** | qui est réveillé quand ça casse, et que lit-il pour comprendre ? |
