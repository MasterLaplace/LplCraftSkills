# Les squelettes par genre

Ce fichier ne se lit pas d'affilée : on y vient avec un genre à écrire. Chaque squelette est un point
de départ copiable, pas un formulaire à remplir case par case. Une section qui n'apporte rien à **ce**
lecteur se retire, même si le squelette la prévoit.

> Les squelettes sont dans des blocs de code, donc sans accents : ils sont faits pour être copiés dans
> un éditeur. Le texte qu'on écrit dedans, lui, porte ses accents s'il est lu par des humains.

## Le rapport, la synthèse

Le lecteur veut savoir où on en est et quoi faire. Il lit le haut, et descend seulement s'il doute.

```markdown
# <Titre qui dit le message, pas le sujet>

> L'essentiel
> - Etat : <ou on en est, en une phrase>
> - Probleme : <ce qui bloque ou ce qui coute, avec son chiffre et son denominateur>
> - Prochain geste : <ce qui se passe ensuite, et qui le fait>

## <Section 1 : sa phrase-message comme titre>

En clair : <le message de la section, sans un seul nombre>

<la preuve : le chiffre avec son unite, son denominateur, sa date et un lien vers sa source ;
 l'artefact reel a cote (extrait, sortie, capture) plutot qu'une description>

Ce que ca ne dit pas : <la limite de la mesure, le perimetre non regarde>

## <Section 2 : ...>
```

La case « ce que ça ne dit pas » est celle qu'on saute, et c'est celle qui protège l'auteur en
réunion : un chiffre dont on a dit la limite ne peut pas être retourné contre lui.

## Le plan de rédaction, avant un document long

Il se fait **avant** d'écrire, et il rend la synthèse vérifiable : si un fait n'entre dans aucun
paragraphe, il n'a rien à faire dans le document.

```markdown
## <Section N : titre>

Budget : <nombre de mots>

Ce que le lecteur doit retenir : <une phrase, qui pourrait etre fausse>

Plan :
1. <paragraphe 1 : son role en quelques mots> (<budget> mots), faits : F1, F2
2. <paragraphe 2 : ...> (<budget> mots), faits : F3

Faits :
- F1 : <le fait> ; source : <fichier:ligne, commande, lien> ; verifie le <date>
- F2 : ...
```

Puis une **passe adversariale** qui rouvre chaque source et marque chaque fait vérifié, corrigé ou
rejeté (voir `challenger-le-sujet`).

Pour un paragraphe qui raconte une contribution personnelle, une forme en trois temps marche bien :
**ce que je croyais, ce que la mesure a montré, ce que j'ai changé.** Elle dit le geste de l'auteur,
et elle prouve qu'il a mesuré au lieu de supposer.

## L'audit

Le lecteur veut savoir ce qui ne va pas, à quel point, et quoi faire. Les normes d'audit ont figé la
forme d'un constat, et elle est bonne pour tout audit, y compris d'un code ou d'une architecture : les
*Global Internal Audit Standards* de l'IIA (2024, norme 14.3) demandent le **critère**, le **constat**,
la **cause racine** quand on peut l'établir, l'**effet** (le risque ou l'exposition), et
l'**importance**, avec sa priorité ; la **recommandation** fait l'objet d'une norme séparée (14.4). Le
*Yellow Book* du GAO américain dit la même chose en quatre mots : critère, constat, cause, effet. Et la
norme demande des constats rédigés de façon succincte, en langage clair.

```markdown
# Audit de <perimetre>, <date>

## Perimetre et methode
- Regarde : <ce qui a ete examine, et comment>
- NON regarde : <ce qui ne l'a pas ete, et pourquoi>
- Etat de reference : <commit, version, environnement>

## Synthese des constats
| # | Constat (une phrase) | Importance | Recommandation |
|---|---|---|---|

## Constat 1 : <une phrase qui dit le probleme>
- Critere : <la regle, la norme ou l'attente, avec sa source>
- Constat : <ce qui a ete observe, avec la preuve : fichier:ligne, commande, capture>
- Cause : <pourquoi c'est arrive, si on le sait ; sinon ecrire "non etablie">
- Effet : <ce que ca expose, pour qui, avec quelle probabilite>
- Importance : <critique / majeure / mineure>, parce que <la raison>
- Recommandation : <le geste, et ce qu'il rend possible>
```

Deux règles propres à l'audit :

- **le périmètre non regardé est écrit.** Un audit qui ne dit pas ce qu'il n'a pas examiné laisse croire
  que ce qu'il ne mentionne pas est sain ;
- **le critère vient avant le constat.** Un écart n'existe que par rapport à une règle, et une règle
  qu'on ne peut pas citer transforme le constat en opinion.

## L'exposé, les slides

Le public écoute quelqu'un qui parle, et ne peut pas relire. Le texte projeté n'est donc pas le texte
dit : l'écran porte le message et sa preuve, la voix porte le reste.

- **un message par slide**, et **le titre est ce message**, en phrase : la structure
  *assertion-preuve* de Michael Alley, un titre-phrase et une preuve visuelle en dessous ;
- **le test du coup d'œil** (Nancy Duarte) : une slide se comprend en trois secondes ;
- **pas de slide de synthèse qui répète** ce qui a déjà été dit, ni en ouverture ni en clôture.
  L'ouverture dit l'état et le problème ; la clôture dit ce qui se passe ensuite ;
- **une grammaire stable d'une slide à l'autre**, quand l'exposé présente plusieurs sujets comparables.
  Pour un état des lieux suivi de propositions, par exemple : **définition, ce qu'on a, ce qui manque, la
  solution** ;
- **pas de deuxième personne** quand on s'adresse à une équipe : on parle du système, pas au public ;
- **la solution, pas son coût**, devant un public qui décide : ce qui deviendra possible, pas le nombre
  de PR, de tickets ou de jours.

```markdown
Slide N
  Titre   : <le message, une phrase complete>
  Visuel  : <la preuve : un graphique, un schema, une capture, un avant/apres>
  Notes   : <ce que l'orateur dit, que l'ecran ne porte pas>
```

**L'alternative aux slides, quand il faut décider** : le mémo narratif. Chez Amazon, une réunion de
décision commence par la lecture silencieuse d'un mémo de six pages rédigé en prose, au lieu d'une
présentation. Un texte suivi oblige l'auteur à relier ses idées, là où des puces les juxtaposent.

## Le post-mortem

Le lecteur veut comprendre ce qui s'est passé, et que ça ne se reproduise pas. Le modèle du livre SRE
de Google est devenu un standard, et son principe compte autant que sa forme : **sans coupable**. On
cherche ce qui a rendu l'erreur possible, pas qui l'a commise.

```markdown
# Post-mortem : <incident en une phrase>

Date : <date> ; Auteurs : <noms> ; Statut : <brouillon / revu / clos>

Resume : <ce qui s'est passe, en 2 ou 3 phrases>
Impact : <qui a ete touche, combien, combien de temps>
Causes racines : <la chaine causale, pas seulement le declencheur>
Declencheur : <ce qui a fait basculer ce jour-la>
Resolution : <ce qui a arrete l'incident>
Detection : <comment on l'a su, et combien de temps apres le debut>

Actions :
| Action | Type (prevenir / detecter / attenuer) | Responsable | Suivi |
|---|---|---|---|

Lecons :
- Ce qui a bien marche : ...
- Ce qui a mal marche : ...
- Ou on a eu de la chance : ...

Chronologie : <horodatee, avec les sources (journal, alerte, message)>
```

La ligne « où on a eu de la chance » est la plus précieuse du modèle : elle nomme les incidents qui ne
sont pas arrivés, donc ceux qu'aucune action ne couvrirait sinon.

## La note de décision

Le lecteur, souvent soi-même dans six mois, veut savoir ce qui a été choisi, pourquoi, et contre quoi.
La forme courte est l'*Architecture Decision Record* de Michael Nygard (2011) : titre, contexte,
décision, statut, conséquences, en une ou deux pages. Une note de décision porte une **date** et ne
se met pas à jour : si la décision change, une nouvelle note remplace l'ancienne, qui reste. C'est ce
qui la rend fiable, et c'est ce qui la destine au wiki (voir `doc-derivee`).

```markdown
# <NNN>. <La decision, en une phrase>

Date : <date> ; Statut : <proposee / acceptee / remplacee par NNN>

## Contexte
<les forces en presence : contraintes, besoin, ce qui est vrai aujourd'hui>

## Options
| Option | Ce qu'elle rend possible | Ce qu'elle empeche ou coute |
|---|---|---|

## Decision
Nous <verbe au present> <ce qui est choisi>, parce que <la raison qui a tranche>.

## Consequences
<ce qui devient plus facile, ce qui devient plus difficile, ce qu'il faudra surveiller>
```

## Le message, la demande

Le lecteur veut savoir ce qu'on attend de lui, sans avoir à le chercher.

- **la demande en première ligne**, formulée comme une question à laquelle on peut répondre ;
- **ce qu'on a déjà vérifié**, en une ligne : c'est ce qui évite la réponse « as-tu essayé de... » ;
- **le contexte ensuite**, seulement ce qu'il faut pour répondre ;
- **une demande par message** : deux demandes dans le même message obtiennent une réponse à la
  première.

```text
Est ce que <question precise> ?

J'ai verifie <ce qui a ete lu, lance, mesure>, et <ce que ca a donne>.
Contexte : <le minimum pour repondre>.
```

## La documentation d'un outil : les quatre besoins de Diátaxis

Le cadre de Daniele Procida range les besoins d'un lecteur de doc sur deux axes : agir ou comprendre,
apprendre ou travailler.

| | pour apprendre | pour travailler |
|---|---|---|
| **agir** | le **tutoriel** : une leçon qui mène le débutant jusqu'à un premier résultat | le **guide pratique** : les étapes d'une tâche précise, pour qui sait déjà |
| **comprendre** | l'**explication** : le pourquoi, le contexte, les alternatives | la **référence** : la description exacte, qu'on consulte sans la lire |

Une page par case. Le mélange le plus fréquent, un tutoriel interrompu par des tableaux de référence,
perd le débutant et agace l'expert. Et la référence, quand elle décrit des options ou des commandes,
se **génère** plutôt que de s'écrire (voir `doc-derivee`).
