---
name: trouver-la-cause
description: >-
  Conduit une enquete avant de corriger : pas de correctif sans cause racine. Couvre la lecture
  integrale du message d'erreur, la reproduction, l'examen des changements recents,
  l'instrumentation des frontieres de composants pour trouver OU ca casse avant POURQUOI, la
  formulation d'une hypothese falsifiable testee une variable a la fois, et les correctifs qui
  masquent au lieu de corriger. A utiliser des qu'il y a un bug, un test rouge, un comportement
  inattendu, un build casse, une lenteur, ou avant de proposer le moindre correctif, et tout
  particulierement sous pression.
---

# Trouver la cause avant de corriger

*En une phrase : corriger un symptome n'est pas un succes partiel, c'est un echec, parce que le
defaut reviendra sous une autre forme et que personne ne saura pourquoi.*

**La loi : aucun correctif avant d'avoir la cause racine.**

La procedure et ses phases sont reprises de **superpowers**
(`github.com/obra/superpowers`, skill `systematic-debugging`), avec les ajouts signales.

## Pourquoi on la viole, et pourquoi c'est perdant

On la viole **sous pression**, et l'argument qui la sauve est arithmetique plutot que moral :
**chaque correctif tente a l'aveugle ajoute une variable a l'enquete.** Trois tentatives, et on ne
sait plus si l'etat courant vient du defaut, de la premiere tentative ou de la troisieme. La methode
n'est pas plus lente que le tatonnement, elle est plus rapide, et l'ecart se creuse a chaque essai.

Les moments ou la tentation est maximale sont exactement ceux ou il faut resister :

- le probleme semble simple (un bug simple a aussi une cause) ;
- un correctif « evident » se presente ;
- on a deja essaye plusieurs choses (donc l'etat est deja pollue) ;
- quelqu'un attend.

## Phase 1 : l'enquete, avant tout correctif

### Lire le message d'erreur en ENTIER

C'est la marche la plus rentable et la plus sautee. **Le message contient souvent la solution
exacte.** La pile d'appels se lit en entier, pas seulement sa premiere ligne ; on note le fichier, la
ligne, le code d'erreur, et le nom exact de ce qui a echoue.

Deux corollaires payes cher :

- **un avertissement n'est pas du bruit.** Il annonce souvent la cause de l'erreur qui suit ;
- **une reponse negative n'est pas une reponse.** Un outil qui rend zero, « aucun resultat » ou
  « inconnu » peut ne pas avoir su lire son entree. Verifier qu'il a regarde au bon endroit avant de
  conclure de son silence.

### Reproduire

Peut-on declencher le defaut de facon fiable ? Quelles sont les etapes exactes ? Est-ce systematique ?

**Si ce n'est pas reproductible, on collecte plus de donnees, on ne devine pas.** Un defaut
intermittent se traite par l'enregistrement, la correlation et les sanitizers (voir
`journal-et-debogueur`), jamais par une serie de correctifs esperes.

### Regarder les changements recents

Presque gratuit, systematiquement oublie : le diff, les derniers commits, une dependance montee de
version, une configuration modifiee, une difference d'environnement entre la machine qui echoue et
celle qui marche.

La question qui cadre : **qu'est-ce qui etait vrai hier et ne l'est plus ?** Et quand « hier » est loin
ou inconnu, l'histoire se lit : `git bisect run` trouve le commit qui a change le comportement,
`git log -S` celui ou une chaine est apparue (voir `explorer-le-code`, section 6).

### Trouver OU ca casse avant de chercher POURQUOI

Dans un systeme a plusieurs composants (interface vers service vers base, tache vers build vers
signature), la premiere erreur est de deviner le composant coupable. La reponse est de **rendre les
frontieres observables**, une fois, puis de lire :

```
Pour CHAQUE frontiere de composant :
  journaliser ce qui ENTRE
  journaliser ce qui SORT
  verifier la propagation de la configuration et de l'environnement

Un seul passage suffit a montrer OU ca casse.
Ensuite seulement : enqueter DANS ce composant.
```

C'est une bissection par frontiere. Elle transforme « ca ne marche pas » en « la valeur est correcte
en entree du composant C et fausse en sortie », ce qui reduit l'enquete d'un facteur dix. Et quand la
forme des donnees compte plus que leur valeur, la vue de l'etat bat le journal (voir
`rendre-l-etat-visible`).

## Phase 2 : une hypothese falsifiable, testee une variable a la fois

*Ajout a la procedure d'origine, parce que c'est la ou une enquete deraille.*

Une hypothese utile dit **ce qu'on observerait si elle etait vraie, et ce qu'on observerait si elle
etait fausse**. « C'est peut-etre le cache » n'est pas une hypothese ; « si c'est le cache, alors
vider le cache fait disparaitre le defaut et le second appel est plus lent que le premier » en est
une.

Deux regles :

- **une variable a la fois.** Changer deux choses et voir le defaut disparaitre ne dit pas laquelle
  l'a corrige, et on vient de creer une dette qu'on ne sait pas nommer ;
- **noter ce qui a ete refute.** Une hypothese eliminee est un resultat. Sans trace, on la retestera,
  et pire, quelqu'un d'autre la retestera.

Et tenir **au moins deux hypotheses** tant qu'aucune n'est refutee : une seule, et on se met a lire les
faits pour elle. La methode generale (hypotheses concurrentes, considerer le contraire, verifier par
une deuxieme route) est dans `challenger-le-sujet`.

**Et avant d'accuser le produit, la bibliotheque ou l'environnement, lire leur source.** Deux
recherches dans le code coutent moins qu'un essai, et la cause d'un blocage est souvent ecrite en
clair. Une accusation sans lecture est une hypothese, pas un diagnostic.

## Phase 3 : corriger la cause, et prouver que le symptome disparait

Le correctif porte sur **la cause identifiee**, pas sur le chemin par lequel elle s'est manifestee.

Puis, et ce n'est pas une formalite : **rejouer le symptome d'origine.** « J'ai change le code » ne
prouve pas « le bug est corrige ». La regle complete est dans `cycle-de-dev`, section de
l'affirmation verifiee.

**Les correctifs qui masquent, a reconnaitre parce qu'ils ont tous l'air de correctifs** :

| Ce qu'on ajoute | Ce que ca cache |
|---|---|
| un `try`/`catch` autour de l'appel qui echoue | l'erreur, sans sa cause, et le symptome ressortira ailleurs |
| un reessai | une condition de course, ou une dependance instable jamais nommee |
| un delai d'attente augmente | la lenteur reelle, jusqu'a ce qu'elle depasse le nouveau delai |
| une attente fixe avant une action | un enchainement mal ordonne, qui redeviendra faux sur une autre machine |
| une valeur par defaut a la place d'une erreur | l'absence de donnee, devenue indiscernable d'une donnee legitime |

Aucun n'est interdit **en connaissance de cause** : un reessai borne sur un reseau est un vrai
mecanisme. Ce qui est interdit, c'est de l'ajouter **a la place** de l'enquete.

## Phase 4 : le test qui empeche le retour

Un correctif sans test de non-regression sera defait par le prochain refactor, et personne ne
saura que la garantie a disparu. Le test s'ecrit **avant** le correctif quand c'est possible, et il
doit avoir ete vu rouge pour la bonne raison (voir `tests-first`).

## Quand la cause racine n'est pas accessible

*Ajout, parce que la loi telle qu'ecrite n'a pas de sortie de secours et qu'il en faut une.*

Il arrive que la cause vive dans une dependance tierce, un pilote, un materiel ou un systeme qu'on ne
controle pas. La loi ne dit pas « ne rien faire ». Elle devient :

1. **borner** ce qu'on sait : quelle est la derniere affirmation verifiee, et ou commence
   l'inconnu ;
2. **contourner en le nommant** : le contournement porte en commentaire la reference du defaut
   externe (numero d'incident, version affectee) et la condition de son retrait ;
3. **ecrire l'ecart** plutot que le masquer : un contournement documente est une dette gerable, un
   contournement silencieux est un piege pour le prochain.

C'est la meme regle que partout ailleurs dans ce pack : **« zero » et « je n'ai pas pu regarder » sont
deux reponses differentes.**

## La porte de sortie

1. je peux **nommer la cause** en une phrase, et dire par quelle observation je l'ai etablie ;
2. je peux **expliquer pourquoi le symptome apparaissait la** et pas ailleurs ;
3. le **symptome d'origine** a ete rejoue, et il a disparu ;
4. un **test** empeche son retour, et il a ete vu rouge ;
5. si la cause n'etait pas accessible, l'ecart est **ecrit**, avec la condition de retrait du
   contournement.

Si le point 1 ou le point 2 manque, l'enquete n'est pas finie, meme si le symptome a disparu. Un
defaut dont on ne sait pas pourquoi il est parti est un defaut qui reviendra.
