---
name: mesure-et-telemetrie
description: >-
  Traite un banc de mesure comme un test de non-regression sur une grandeur continue : budget
  falsifiable, decoupage qui explique la cause, protocole qui resiste au bruit machine, ligne de
  base appariee, et comptage d'instructions plutot que de temps en CI. Couvre le profilage avant
  optimisation (loi d'Amdahl), les specificites GPU/CUDA (asynchronisme, evenements, transferts,
  roofline), la telemetrie en production (metrique / journal / trace, cardinalite, signaux
  actionnables), et ce qui doit ou ne doit PAS disparaitre d'un build de production. A utiliser
  pour ecrire ou lire un benchmark, chasser une lenteur, comparer deux implementations, poser des
  metriques, ou preparer un artefact de production.
---

# Mesurer pour décider : bancs, profils, télémétrie

*En une phrase : un banc de mesure est un test de non-régression sur une grandeur continue, et s'il est
bien découpé il ne dit pas seulement « c'est plus lent », il dit pourquoi.*

C'est la bonne façon d'y penser. Un test binaire répond oui ou non ; un banc répond *« est-ce que je
régresse ou je progresse »* et, découpé correctement, **désigne la cause**.

## 1. Ce qui fait qu'un banc EST un test, et non un nombre

| Un nombre | Un test |
|---|---|
| « 4,2 ms » | « p99 sous 5 ms sur le jeu `large`, sinon le merge est refusé » |
| joué à la main quand on y pense | joué en intégration continue, comme la suite |
| une valeur | une **distribution** : médiane, p95, p99, variance, nombre de tirages |

> **p99** veut dire : la valeur sous laquelle tombent 99 % des mesures. C'est ce que vit le centième
> utilisateur, et c'est presque toujours ce qui compte plus que la moyenne.

**Sans budget, un banc n'est pas falsifiable**, donc ce n'est pas un critère d'acceptation mais une
courbe qu'on regarde dériver. Le budget est un critère au sens de `tests-first` : « 1 000 éléments en
moins de 200 ms au p99 sur la machine d'intégration ».

Et trois différences avec un test ordinaire, qu'il faut tenir :

1. **la sortie est continue**, donc il faut un seuil **et** une tolérance. Sinon il rougit sur du bruit,
   et un test qui rougit sur du bruit sera désactivé ;
2. **il dépend de la machine**, donc il exige un protocole, voir la section 3 ;
3. **il ne prouve rien sur la justesse.** Un banc vérifie qu'on va vite, pas qu'on a raison, et la
   version la plus rapide est souvent celle qui ne calcule rien. **Toujours doubler un banc d'un test de
   correction** sur le même code.

## 2. Le découpage est ce qui transforme un banc en diagnostic

Un banc qui rend **un** nombre pour tout le pipeline dit « c'est 18 % plus lent ». Inutilisable. Le même
banc découpé par étage dit « l'analyse est identique, la transformation a doublé, l'émission est
identique », et là, on sait où regarder.

**La règle : découper selon les causes qu'on pourrait corriger**, pas selon l'élégance du découpage. Un
étage qu'on ne peut pas modifier séparément n'a pas besoin de sa mesure.

### Normaliser, pour comparer entre tailles

Une mesure brute mélange « c'est plus lent » et « l'entrée a grossi ». Les grandeurs **dérivées** séparent
les deux : temps **par élément**, octets **par seconde**, instructions **par élément**, défauts de cache
**par élément**. C'est ce qui permet de comparer deux tirages qui n'ont pas la même entrée, et c'est ce
qui fait qu'un banc reste lisible six mois plus tard.

### La FORME du changement nomme la cause

C'est le vrai rendement d'un banc bien découpé et bien instrumenté :

| Ce que la mesure montre | Ce que ça désigne |
|---|---|
| temps doublé, **instructions constantes** | on est devenu **mémoire** : cache, localité, faux partage |
| **instructions doublées**, temps doublé | l'algorithme ou le code généré a changé |
| ne bouge qu'**au-delà d'une taille** | un niveau de cache déborde, ou un seuil d'allocation |
| **variance** qui explose, médiane stable | contention, migration de cœur, bridage thermique, ramasse-miettes |
| p50 stable, **p99 multiplié par dix** | une file d'attente, un verrou, un réessai |
| linéaire puis **quadratique** | une recherche linéaire dans une boucle, une concaténation coûteuse |

Aucune de ces lignes ne se lit sur un nombre unique. Toutes se lisent sur un banc découpé qui publie sa
distribution et au moins un compteur matériel.

## 3. Les quatre façons dont un banc mente, et elles rendent toutes un nombre plausible

### a. Le compilateur supprime ton calcul

Le défaut numéro un en C++ : le résultat n'est pas utilisé, donc l'optimiseur retire le calcul, et le banc
annonce **0,3 ns**. Le nombre est faux et il a l'air formidable.

```cpp
// FAUX : rien ne consomme le resultat.
for (auto _ : state) { ComputeChecksum(buffer); }

// CORRECT : la valeur est rendue opaque a l'optimiseur.
for (auto _ : state) {
    auto value = ComputeChecksum(buffer);
    benchmark::DoNotOptimize(value);
}
benchmark::ClobberMemory();   // si le code ecrit en memoire
```

**Le contrôle qui l'attrape** : un résultat trop beau, d'un ordre de grandeur, est un bug de banc jusqu'à
preuve du contraire. Vérifier en lisant l'assembleur généré, ou en faisant varier la taille d'entrée, un
temps qui ne bouge pas avec l'entrée ne mesure rien.

### b. Le bruit de la machine

Fréquence turbo et bridage thermique, migration entre cœurs, hyperthreading, autres processus, premiers
accès qui paient les défauts de page. Le protocole minimal : **itérations de chauffe**, **cœur épinglé**,
gouverneur de fréquence fixe, machine au repos, et **N tirages avec la variance publiée**. Détails et
commandes dans `references/protocole-de-mesure.md`.

### c. Le micro-banc n'est pas ton programme

Dans un micro-banc, le cache est chaud, la branche est parfaitement prédite parce que l'entrée se répète,
et l'allocateur est déjà rodé. Dans l'application, rien de tout ça. C'est ainsi qu'on obtient un micro-banc
**trois fois plus rapide** pour **0 %** de gain de bout en bout.

> **Un micro-banc CLASSE des candidats. Une mesure de bout en bout DÉCIDE.** Ne jamais expédier une
> optimisation sur la foi du seul micro-banc.

### d. La ligne de base non appariée

Deux tirages faits à deux moments différents, sur deux arbres différents, ne sont pas comparables, et
l'écart qu'on lit peut venir d'un TROISIÈME changement. La discipline :

- **entrelacer** A et B dans la même session (A, B, A, B...) plutôt que tous les A puis tous les B : ça
  neutralise la dérive thermique et la charge de fond ;
- **même machine, même arbre**, et **enregistrer l'état de l'arbre avec la mesure** : commit, présence de
  modifications non commitées, empreinte du diff. Deux mesures ne sont comparables que si les deux le
  portent ;
- **refuser de conclure** quand un fichier modifié est présent dans les deux bras : il serait des deux
  côtés, donc le pairage ne peut rendre que « pareil ».

## 4. GPU et CUDA : quatre pièges qui rendent des accélérations fantômes

1. **Les lancements sont asynchrones.** Sans synchronisation explicite ou paire d'événements, on mesure le
   **temps de mise en file**, pas le noyau. C'est la source des « 200 fois plus rapide » impossibles.
2. **La première exécution paie la création du contexte et la compilation à la volée.** Chauffer, toujours,
   et ne jamais publier le premier tirage.
3. **Mesurer les transferts SÉPARÉMENT du calcul.** Un noyau cinquante fois plus rapide dont les transferts
   dominent rend un gain de bout en bout nul, et c'est le cas le plus courant. Trois nombres : hôte vers
   périphérique, calcul, périphérique vers hôte.
4. **Savoir de quel côté du toit on est.** Comparer la bande passante atteinte à la bande passante crête :
   si on est **limité par la mémoire**, optimiser l'arithmétique ne peut rien donner, et inversement. C'est
   la mesure qui évite des semaines d'optimisation sur le mauvais axe.

Les outils, dans cet ordre : `nsys` pour la **chronologie** (où passe le temps, y compris les trous), puis
`ncu` pour les **compteurs d'un noyau**. `-lineinfo` corrèle le profil au source et ne coûte rien en
performance. L'occupation n'est pas le débit : une occupation élevée peut accompagner un débit médiocre.

## 5. Avant d'optimiser, le filtre qui coûte une minute

> **Quelle FRACTION du temps total occupe ce que je veux optimiser ?**

Diviser par deux quelque chose qui pèse 5 % du total gagne 2,5 %. Cette question, posée avant d'écrire une
ligne, tue gratuitement la plupart des idées d'optimisation, et elle désigne la seule qui vaut le coup.
**Le profileur d'abord, l'intuition jamais** : sur ce point, la mesure contredit l'intuition la moitié du
temps, y compris chez des gens expérimentés.

Et le rappel de `commencer-ferme` : **la précision de type est gratuite, l'optimisation de code se paie**
en lisibilité et en bugs. Elle exige donc une mesure, jamais une conviction.

## 6. En intégration continue, le temps est trop bruyant : compter les instructions

Sur un exécuteur partagé, le temps varie de 20 à 50 % d'une exécution à l'autre. Un seuil sur le temps y
produit des alertes fausses, donc il sera désactivé. Deux réponses, cumulables :

- **compter les instructions plutôt que le temps** (`perf stat -e instructions`, `cachegrind`). C'est
  quasi déterministe, donc un seuil serré y est tenable, et une régression algorithmique s'y voit
  parfaitement. Ça ne dit rien de la latence réelle, mais ce n'est pas ce qu'on lui demande ;
- **une machine dédiée** pour les mesures de temps, hors intégration partagée, avec des tirages entrelacés.

Et dans les deux cas : **publier la variance et le nombre de tirages.** Un chiffre sans son dénominateur
n'est pas défendable.

## 7. Télémétrie en production, et pourquoi elle trouve des bugs

Trois supports, trois usages, et les confondre coûte cher :

| Support | Ce que c'est | Le piège |
|---|---|---|
| **métrique** | un nombre agrégé dans le temps : compteur, jauge, histogramme | **la cardinalité** : une étiquette à valeurs illimitées (identifiant de requête, d'utilisateur) fait exploser le stockage. Jamais d'identifiant en étiquette |
| **journal** | un événement avec son contexte | le volume, et le filtre sur une phrase, voir `journal-et-debogueur` |
| **trace** | un chemin causal à travers les composants | le coût, d'où l'échantillonnage |

Ce qu'il faut mesurer au minimum : **latence, trafic, taux d'erreur, saturation**, plus les **compteurs qui
répondent à « ce chemin sert-il encore ? »**, c'est la règle de `concevoir-avant-coder` : un mode sans
compteur est une devinette avec un drapeau.

Deux règles symétriques : **un compteur que ni alerte ni tableau de bord ne lit est du bruit**, et **une
alerte sur laquelle personne n'agit doit disparaître**, même critère que le niveau `ERROR`.

**Et le mécanisme par lequel la télémétrie trouve des bugs** n'est pas la valeur d'une métrique, c'est **le
changement de sa forme après un déploiement**. Une latence dont le p99 se détache du p50, un compteur de
chemin de repli qui se met à monter, une distribution qui devient bimodale : chacun est un défaut trouvé
**avant** qu'un utilisateur ne le signale. C'est pour ça que les métriques doivent avoir une **ligne de
base** : sans historique, une valeur ne dit rien.

## 8. Le build de production : ce qui part, et surtout ce qui RESTE

C'est ici qu'il faut découper trois choses souvent confondues :

| Famille | Dans l'artefact de production ? |
|---|---|
| **le banc de mesure** et son harnais | **non.** C'est de l'outillage de développement |
| **l'instrumentation lourde** : traceur par appel, suivi d'allocations, couches de validation, assertions chères, empoisonnement mémoire | **non par défaut**, mais **activable**, et le chemin d'activation est documenté |
| **la télémétrie** : métriques, santé, journal d'avertissement et d'erreur structuré, traces échantillonnées | **OUI, et c'est non négociable** |

La troisième ligne est la correction importante : **la production est le seul endroit où le monitoring
sert.** L'y retirer, c'est supprimer exactement l'outil qui trouve les problèmes. Ce qui contient son coût
n'est pas la suppression, c'est l'**agrégation** et l'**échantillonnage**.

**Et le vrai motif du nettoyage n'est pas la performance, c'est la SURFACE D'ATTAQUE.** Ce qui doit
disparaître pour cette raison : points d'entrée de débogage et d'administration, port de profileur, piles
d'appels renvoyées à l'utilisateur, pages d'erreur verbeuses, identifiants et données de test, crochets de
test, chaînes internes inutiles. Une machinerie de diagnostic laissée active en production est une porte,
pas une lenteur.

> **« On a pensé à tout virer » est un espoir, pas une porte.** Ce qui en fait une porte : un **contrôle
> automatique sur l'artefact**, l'unité d'outillage est absente, aucun point d'entrée de débogage n'est
> routé, le harnais de banc n'est pas embarqué. Vérifié par l'intégration continue, pas par la mémoire de
> celui qui a construit. C'est la même exigence que « un garde qu'aucune commande ne lance n'est pas un
> garde ».

## La porte de sortie

1. chaque banc porte un **budget**, une **distribution** et un **nombre de tirages** ;
2. le découpage permet de **nommer une cause**, pas seulement de constater un écart ;
3. toute comparaison A/B est **appariée et entrelacée**, et porte l'état de l'arbre ;
4. aucune optimisation n'est expédiée sans une mesure **de bout en bout** ;
5. l'artefact de production **garde** sa télémétrie et **perd** sa machinerie, vérifié par un contrôle
   automatique.
