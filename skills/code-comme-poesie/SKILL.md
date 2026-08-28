---
name: code-comme-poesie
description: >-
  Ecrit et relit du code lisible : noms longs et exacts, clauses de garde et sortie anticipee,
  une seule altitude d'abstraction par fonction, zero commentaire qui paraphrase, doc de contrat
  (Doxygen / XML doc / TSDoc / docstring) sur la seule frontiere publique, echec bruyant et
  precoce. A utiliser pendant l'ecriture, pendant une revue, ou quand du code existant est
  difficile a lire : imbrication profonde, noms vagues, commentaires qui expliquent le comment,
  fonctions qui font deux choses.
---

# Le code comme poésie

*En une phrase : tout ce qui peut être porté par le code doit l'être par le code, parce que le reste
finira par mentir.*

Un poème ne s'explique pas en note de bas de page : il porte son sens dans ses mots. Le code aussi.
**La doc et les commentaires peuvent mentir, le code ne le peut pas**, non parce qu'il serait plus
honnête, mais parce qu'il est le seul texte que la machine exécute. Ce qui reste dans un texte à côté
est une dette qui pourrira en silence.

## 1. Les noms : longs et exacts battent courts et vagues

Un nom est la seule documentation qui ne peut pas se désynchroniser, parce qu'on la lit à chaque
usage.

| Vague | Exact |
|---|---|
| `process(d)` | `computeProratedAmountForPartialMonth(contract)` |
| `data`, `info`, `tmp`, `result` | `pendingReviewsByManager`, `rawPayrollExport` |
| `handle()`, `manage()`, `doWork()` | `rejectExpiredSessions()`, `publishSalaryReviewOpened()` |
| `flag`, `check` | `isEligibleForRetroactivePay`, `hasReachedApprovalThreshold` |

Quatre règles :

- **la longueur du nom suit la portée.** Un `i` de boucle sur trois lignes est parfait ; un champ de
  classe nommé `i` est une énigme ;
- **un nom qui contient « et » décrit deux fonctions.** `validateAndSave` fait deux choses, donc on ne
  peut ni valider sans sauver, ni tester l'un sans l'autre. Le nom l'avait dit ;
- **le vocabulaire du domaine, pas celui de l'informatique.** `SalaryReview`, pas `DataRecord`. Un nom
  technique là où un mot métier existe fait perdre la trace du besoin ;
- **aucune abréviation qui ne soit pas du domaine.** `qty` non ; `HTTP`, `SIREN`, `URSSAF` oui.

**Le nommage est le meilleur détecteur de mauvaise conception qui existe** : quand un nom exact est
impossible à trouver, c'est presque toujours que la chose n'a pas une seule responsabilité. Ne pas
forcer le nom, regarder ce qu'il essaie de dire.

## 2. Clauses de garde : sortir tôt, et mieux, rendre l'invalide impossible

Une *clause de garde* est un refus placé en tête de fonction, qui traite le cas anormal et sort, pour
que le cas normal se lise à plat en dessous.

```csharp
// Avant -- le cas nominal est enterre sous les conditions
if (user != null) {
    if (user.IsActive) {
        if (contract != null) {
            return Compute(user, contract);
        } else { throw new ArgumentNullException(nameof(contract)); }
    } else { throw new InvalidOperationException("inactive user"); }
} else { throw new ArgumentNullException(nameof(user)); }

// Apres -- les refus d'abord, le sens ensuite, a plat
if (user is null) throw new ArgumentNullException(nameof(user));
if (contract is null) throw new ArgumentNullException(nameof(contract));
if (!user.IsActive) throw new InvalidOperationException($"user {user.Id} is inactive");

return Compute(user, contract);
```

Trois règles : **jamais d'`else` après un `return` ou un `throw`** ; **deux niveaux d'imbrication au
maximum** dans une fonction, au-delà on extrait ; **le cas nominal à plat, en fin de fonction**, là où
on le cherche.

**Et le niveau au-dessus, qui rend la garde inutile** : quand un état invalide ne peut pas être
représenté, il n'y a plus rien à garder. Un type qui ne peut pas être nul, un entier positif qui est
son propre type, une plage de dates dont le constructeur refuse l'inversion, la garde est alors
écrite **une fois**, à la frontière, au lieu d'être répétée à chaque usage et oubliée une fois sur
trois. C'est le sujet de `commencer-ferme`.

## 3. Une fonction, une altitude d'abstraction

Le défaut le plus courant n'est pas la longueur, c'est le **mélange d'altitudes** : une fonction qui
orchestre trois étapes métier et, au milieu, décale un octet.

Le signal fiable : **tu as besoin d'un commentaire pour savoir où tu en es** (`// etape 2 : ...`). Ce
commentaire est un nom de fonction qui n'a pas été écrit. On extrait, et le commentaire disparaît avec
le problème.

Une fonction bien découpée se lit comme un sommaire : chaque ligne dit **quoi**, et chaque nom appelé
mène au **comment**.

## 4. Commentaires : la règle n'est pas « zéro », c'est « aucun qui paraphrase »

Un commentaire qui redit le code est pire qu'inutile : il double la surface à maintenir, et il
**divergera**, parce que rien ne casse quand il mente.

```cpp
i++;  // incremente i                          <- a supprimer
// boucle sur les utilisateurs                 <- a supprimer, la boucle le dit
```

**Quatre cas, et quatre seulement, où un commentaire porte ce que le code ne peut pas porter :**

1. **le POURQUOI non déductible** : pourquoi ce seuil vaut 3, pourquoi cet ordre précis ;
2. **une contrainte externe** : un bug d'une bibliothèque, une clause d'un standard, une règle légale,
   une limite matérielle. Avec sa **référence**, numéro de norme, d'incident, d'article ;
3. **un invariant que le type ne peut pas exprimer** : « appelé sous le verrou X », « le tableau est
   trié par date décroissante, dont dépend la dichotomie ci-dessous » ;
4. **un avertissement coûteux** : « ne pas réordonner, la seconde écriture doit être visible après la
   première sur ce matériel ». Typiquement C, C++ et assembleur, où l'intention n'est pas dans le
   code.

```cpp
// Le contournement vient du bug #4412 de libfoo < 2.3 : un fsync sur un fichier
// ouvert en O_APPEND y perd la derniere page. Retirable quand le socle passera en 2.3.
flush_via_temp_file(path);
```

**Tout le reste est une fonction bien nommée qui n'a pas été extraite.** Et deux interdits : le **code
mort commenté** (l'historique de version existe pour ça, et lui ne mente pas) et le **TODO sans
référence d'item**, un TODO anonyme n'a pas de propriétaire, donc il ne sera jamais fait, mais il sera
lu mille fois.

## 5. La doc de contrat, sur la frontière publique et là uniquement

Doxygen, XML doc, TSDoc, docstring : même rôle selon le langage, **décrire un contrat à quelqu'un qui
n'ouvrira pas le code**. Elle répond à trois questions, jamais à une quatrième :

1. **ce que ça garantit**, la promesse, en termes observables ;
2. **ce que ça exige**, les conditions d'entrée, les unités, les plages, la propriété de la mémoire ;
3. **ce que ça peut lever ou retourner en erreur**.

**Ce qu'elle ne décrit jamais : le comment.** Le comment est en dessous, et il changera.

```cpp
/**
 * @brief Calcule le montant proratise pour un mois partiel.
 * @param contract Contrat actif ; la periode doit etre incluse dans sa validite.
 * @param period Plage fermee, en jours ouvres.
 * @return Montant en centimes, arrondi au centime superieur.
 * @throws std::invalid_argument Si la periode sort de la validite du contrat.
 * @note L'arrondi superieur est impose par la convention collective, pas par un choix technique.
 */
```

**Pas de doc de contrat sur les fonctions privées.** Elles n'ont pas d'appelant externe, leur nom et
leurs types suffisent, et une doc privée est un duplicata de plus à maintenir. La déclinaison par
langage est dans `references/doc-par-langage.md`.

**Et une part de ce contrat n'a pas besoin d'être écrite : elle se déclare.** Ce qu'un `const`, un
`[[nodiscard]]`, un `explicit` ou un type fort disent, la doc n'a pas à le redire, et eux ne peuvent
pas mentir. Voir `commencer-ferme`. Pour tout ce qui déborde de la signature (surface de CLI, README,
messages d'erreur), voir `doc-derivee`.

## 6. Le duplicata de vérité, le défaut qui ne casse jamais

**Dès qu'un texte écrit à la main décrit un code, il finit par mentir, et rien ne le signale.** Un
compilateur casse quand une signature change ; un paragraphe ne casse jamais. C'est vrai d'une doc,
d'un README, d'une liste dans un gabarit, d'une table de constantes recopiée dans un outil.

La réponse n'est pas la vigilance, elle échoue toujours à la longue. Il y en a deux :

- **dériver** : la doc, la liste, la table sont **générées** depuis la source qui fait autorité ;
- **apparier** : ce qui reste écrit à la main est comparé par un test à sa source, **avec un plancher**
  : le test doit refuser un corpus vide, sinon il passe au vert le jour où il ne compare plus rien.

Et le corollaire, quand ni l'un ni l'autre n'est possible : **écrire l'écart plutôt que le masquer.**
Un document qui dit où il peut mentir vaut infiniment mieux qu'un document qu'on croit exact.

## 7. Échouer bruyamment, tôt, et en nommant quoi et où

- **jamais de `catch` nu** qui avale. Un `catch` qui n'ajoute ni contexte ni décision effface la cause
  et déplace le symptôme loin de son origine ;
- **un message d'erreur nomme la valeur et le contexte.** `"contract 4821: period 2026-02-01..2026-02-28
  outside validity 2026-03-01.."` bat `"invalid period"` d'un facteur dix au débogage ;
- **ne jamais retourner une valeur neutre à la place d'une erreur** (`0`, `null`, une liste vide,
  `false`). C'est indiscernable d'un résultat légitime. **« Zéro » et « je n'ai pas pu regarder » sont
  deux réponses différentes**, et les confondre produit des chiffres faux qui ont l'air justes ;
- **échouer tôt** : valider à la frontière, une fois, plutôt qu'à chaque usage.

## 8. Ce qu'on regarde en relisant, dans cet ordre

Du plus cher au moins cher à corriger plus tard :

1. **le contrat** : la signature dit-elle la vérité sur ce que ça fait et ce que ça exige ?
2. **les cas limites** : vide, nul, zéro, négatif, très grand, concurrent, en double ;
3. **les erreurs** : que se passe-t-il quand ça rate, qui l'apprend, avec quel message ?
4. **les noms** : un lecteur qui ne connaît pas ce code comprend-il sans descendre dans le corps ?
5. **le style** : en dernier, et **s'il se discute en revue, c'est qu'il manque au formateur
   automatique.** Un style appliqué par un outil ne consomme pas de temps humain ; un débat de style en
   revue consomme celui qu'on n'a plus pour les points 1 à 3.

## La porte de sortie

Avant de rendre le code, ces six réponses doivent exister :

1. un lecteur qui ne connaît pas ce code comprend **ce que fait chaque fonction sans descendre dans son
   corps**, en lisant seulement sa signature ;
2. l'invalide est **impossible** là où il pouvait l'être, et gardé tôt là où il ne pouvait pas ;
3. chaque fonction se raconte **à une seule altitude**, sans « et » dans son résumé ;
4. **aucun commentaire ne paraphrase le code** : ceux qui restent tombent dans les quatre cas, et il n'y a
   ni code commenté, ni journal de modifications en commentaire ;
5. la **doc de contrat** couvre la frontière publique et rien d'autre, elle dit ce que la fonction exige
   et ce qu'elle garantit, jamais comment elle s'y prend ;
6. quand ça rate, quelqu'un l'apprend, **tôt**, avec quoi et où.

Et le test qui vaut pour tout le skill, parce qu'il attrape les cinq autres : **si un nom exact est
impossible à trouver, ce n'est pas le nom qui résiste, c'est la chose nommée.** Une fonction qu'on ne
sait pas nommer en fait deux ; un paramètre qu'on ne sait pas nommer n'a rien à faire là.
