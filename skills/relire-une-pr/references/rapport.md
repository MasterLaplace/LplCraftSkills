# Le gabarit du rapport de revue

Le rapport s'écrit pour la personne qui a demandé la revue, pas pour l'auteur de la PR : c'est elle qui
décide de ce qui part sur la forge. Il tient sur un écran en tête, puis une carte par remarque.

## Le squelette

```markdown
# Revue de <depot>#<N> : <titre de la PR>

Relu : commit <sha court>, base <sha court>. Rien n'a ete publie.

<Une phrase : le verdict. Exemple : un defaut bloquant, une affirmation fausse dans la description,
deux questions.>

## Bloquant

### 1. <Le constat, en une phrase qui pourrait etre fausse>
- Constat : <ce qui est faux, dans quel etat d'entree>
- Preuve : <fichier:ligne relu a l'instant, ou la commande et sa sortie>
- Correctif : <le plus petit changement qui retire la cause, en esquisse>
- Test : <le test qui l'aurait attrape, idealement sur une fixture qui existe deja>

## A corriger

### 2. <...>
- Constat / Preuve / Correctif

## Questions

### 3. <...>
- Constat : <ce que la PR annonce, et ce que le code fait>
- Ce qui me ferait changer d'avis : <...>

## Preferences

### 4. <...> (preference, non bloquante)

## Verifie, rien a redire
- <l'affirmation de la description, et comment elle a ete verifiee>

## Ecartes
- <ce qui a ete juge et n'est pas remonte> : <la raison (convention du depot, hors perimetre, non observe)>

## Pas verifie
- <ce que la revue n'a pas pu faire> : <ce que ca laisse ouvert>

## Passe hostile
<Par qui, sur quels constats, et ce qu'elle a change : confirmes, infirmes, nuances, rates trouves.
Ou : pas de passe hostile, et pourquoi.>
```

## Trois règles de forme

- **le titre d'une remarque est son constat**, pas son sujet. « La tuile affiche le total global quand
  un seul projet est filtré » se lit sans la carte ; « Problème de la tuile » oblige à la lire ;
- **la même forme pour chaque carte**, pour qu'une preuve absente se voie (`se-faire-comprendre`,
  section 4) ;
- **les chemins de fichier disent à quel commit ils renvoient** quand le lecteur n'a pas la PR sous les
  yeux : un `fichier:ligne` de la copie de travail du lecteur peut désigner une autre version.
