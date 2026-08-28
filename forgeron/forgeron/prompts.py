"""What the agent is told, and the shape of what it must answer.

Every run answers a schema, never prose. That is the whole reason the driver can
be a state machine: reading a verdict out of a paragraph is a parser nobody can
keep correct, and a bot that mis-reads its own success is a bot that asks for
review on nothing.

The rails live in CONTRACT and are repeated in every prompt on purpose. A rule
stated once, in a system prompt, is a rule the model can lose behind a long tool
transcript.
"""

from __future__ import annotations

from typing import Any

from .model import Feedback, FeedbackKind, IssueRef, Record

CONTRACT = """\
Tu es lance SANS SURVEILLANCE par un orchestrateur (forgeron). Personne ne repondra
a une question posee dans ta reponse finale : le seul canal vers l'humain est la
forge (issue, pull request), et le seul canal vers l'orchestrateur est le JSON
final impose par le schema.

Autorisations, strictement bornees :
- tu peux commiter et pousser SUR LA BRANCHE {branch} et sur elle seule ;
- tu ne pousses JAMAIS sur {base}, tu ne fais JAMAIS de push --force, tu ne merges
  JAMAIS, tu ne fermes JAMAIS l'issue, tu ne modifies JAMAIS .github/workflows/ ;
- tu restes dans {worktree}. C'est un git worktree dedie : le checkout de l'humain
  est ailleurs et ne doit pas etre touche ;
- pas de `git rebase`, pas de `git reset --hard` sur du deja pousse : un humain lit
  ce diff au fur et a mesure, et reecrire l'historique sous ses yeux annule sa revue.

Methode, non negociable :
- invoque le skill `cycle-de-dev` (outil Skill) avant d'ecrire une ligne, et suis
  ses portes de sortie. Il delegue aux autres skills, laisse-le faire ;
- une affirmation se prouve : tu ne declares pas une porte franchie sans avoir lance
  a l'instant la commande qui le montre, et tu recopies cette commande dans
  `commands_run`. « ca devrait marcher » n'est pas un resultat ;
- aucun avertissement nouveau ne franchit un commit ;
- si tu es bloque (ambiguite, dependance absente, acces refuse), tu reponds
  verdict="blocked" avec `blocked_reason`. Deviner coute plus cher que demander.

Commits : Conventional Commits, en francais, sans ligne Co-Authored-By et sans
mention d'un outil d'IA. L'auteur du depot est MasterLaplace.
"""

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "branch_slug": {"type": "string", "description": "kebab-case, 2 a 5 mots, sans prefixe"},
        "kind": {"type": "string", "enum": ["feat", "fix", "refactor", "docs", "test", "chore", "perf"]},
        "pr_title": {"type": "string"},
        "pr_body": {"type": "string", "description": "markdown : contexte, approche, criteres, hors-perimetre"},
        "acceptance": {
            "type": "array",
            "items": {"type": "string"},
            "description": "criteres falsifiables, chacun verifiable par une commande",
        },
        "files_expected": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "vide si et seulement si rien ne bloque le codage",
        },
    },
    "required": ["branch_slug", "kind", "pr_title", "pr_body", "acceptance", "risk", "questions"],
    "additionalProperties": False,
}

WORK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ready_for_review", "blocked", "no_change_needed"]},
        "summary": {"type": "string", "description": "un paragraphe, en francais"},
        "commands_run": {"type": "array", "items": {"type": "string"}},
        "acceptance": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "met": {"type": "boolean"},
                    "evidence": {"type": "string", "description": "la sortie ou la commande qui le prouve"},
                },
                "required": ["criterion", "met", "evidence"],
                "additionalProperties": False,
            },
        },
        "pushed": {"type": "boolean"},
        "blocked_reason": {"type": "string"},
        "answers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "une reponse par remarque de revue traitee, dans l'ordre recu",
        },
    },
    "required": ["verdict", "summary", "commands_run", "acceptance", "pushed"],
    "additionalProperties": False,
}

WRAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "followups": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ce qui reste et qui merite sa propre issue",
        },
    },
    "required": ["summary", "followups"],
    "additionalProperties": False,
}


def contract(record: Record, base: str, exception: str = "") -> str:
    """The rails. `exception` widens exactly one of them, for exactly one phase.

    Written as an addition rather than by editing the rule, so the rule and its
    single exception are read together and the exception cannot outlive the phase
    that needed it.
    """
    text = CONTRACT.format(branch=record.branch or "(a creer)", base=base,
                           worktree=record.worktree)
    if exception:
        text += "\nEXCEPTION, valable UNIQUEMENT pour ce tour :\n" + exception
    return text


def plan_prompt(issue: IssueRef, answers: tuple[Feedback, ...] = ()) -> str:
    parts = [
        "PHASE 1 sur 4 : CADRER. Tu ne modifies AUCUN fichier dans cette phase.",
        "",
        f"Issue {issue.repo}#{issue.number} : {issue.title}",
        f"URL : {issue.url}",
        "",
        "Corps de l'issue :",
        _quote(issue.body or "(vide)"),
        "",
        "Invoque le skill `cadrer-et-planifier`, explore le depot pour te fonder sur le code reel,",
        "et rends le plan au format impose.",
        "",
        "Deux regles qui decident du reste :",
        "- `acceptance` ne contient que des criteres FALSIFIABLES, chacun verifiable par une commande.",
        "  « le code est propre » n'en est pas un, « la suite passe deux fois d'affilee » en est un ;",
        "- `questions` n'est PAS un endroit ou etre poli : tu n'y mets que ce qui, sans reponse,",
        "  te ferait construire potentiellement la mauvaise chose. Si tu en mets une, aucun code ne",
        "  sera ecrit et un humain sera interroge. Une liste vide est la reponse normale.",
    ]
    if answers:
        parts += ["", "Un humain a repondu depuis ta derniere tentative :", _feedback_block(answers)]
    return "\n".join(parts)


def implement_prompt(issue: IssueRef, plan: dict[str, Any], pr_url: str) -> str:
    criteria = "\n".join(f"- {item}" for item in plan.get("acceptance", ())) or "- (aucun)"
    return "\n".join([
        "PHASE 2 sur 4 : IMPLEMENTER. La pull request en brouillon est deja ouverte,",
        f"un humain peut la lire pendant que tu travailles : {pr_url}",
        "",
        f"Issue {issue.repo}#{issue.number} : {issue.title}",
        "",
        "Criteres d'acceptation, tires de TON plan et deja publies dans la pull request :",
        criteria,
        "",
        "Invoque `cycle-de-dev` et suis-le : test rouge d'abord quand le sujet s'y prete, code ensuite,",
        "doc derivee, et une porte de sortie prouvee par une commande a chaque etape.",
        "",
        "Termine par des commits Conventional Commits et un `git push` sur ta branche.",
        "`pushed` doit dire la verite : l'orchestrateur le verifie contre l'etat de git.",
    ])


def revise_prompt(issue: IssueRef, feedback: tuple[Feedback, ...], round_number: int) -> str:
    return "\n".join([
        f"PHASE 3 sur 4 : REVISER, tour {round_number}.",
        f"Un humain a relu ta pull request pour {issue.repo}#{issue.number} et a laisse ceci :",
        "",
        _feedback_block(feedback),
        "",
        "Pour CHAQUE remarque, dans l'ordre : soit tu la traites, soit tu expliques pourquoi tu ne le",
        "fais pas. Une remarque sautee en silence est la seule reponse interdite.",
        "",
        "Invoque `trouver-la-cause` si la remarque signale un bug : pas de correctif sans cause racine,",
        "et un correctif qui masque le symptome sera renvoye par la revue suivante.",
        "",
        "Remplis `answers` avec une ligne par remarque, dans l'ordre recu : ces lignes sont publiees",
        "telles quelles sur la pull request, c'est ta reponse au relecteur.",
        "Puis commite et pousse sur ta branche.",
    ])


def fix_checks_prompt(issue: IssueRef, failing: tuple, logs: str, attempt: int,
                      max_attempts: int) -> str:
    names = ", ".join(f"`{run.name}`" for run in failing) or "(inconnu)"
    return "\n".join([
        f"PHASE 3b : L'INTEGRATION CONTINUE EST ROUGE. Tentative {attempt} sur {max_attempts}.",
        f"Issue {issue.repo}#{issue.number}. Jobs en echec : {names}.",
        "",
        "Voici les journaux, tronques par la fin (donc l'erreur y est, la mise en route non) :",
        "",
        "```",
        logs.strip() or "(aucun journal recuperable)",
        "```",
        "",
        "Invoque `trouver-la-cause`. Lis le message d'erreur EN ENTIER avant de toucher quoi que",
        "ce soit : un correctif pose sur la premiere ligne rouge repare le symptome et laisse la",
        "cause en place, et le job repassera rouge au tour suivant.",
        "",
        "Trois pieges a nommer explicitement si tu les rencontres, plutot qu'a contourner :",
        "- si le job echoue pour une raison d'ENVIRONNEMENT (secret absent, quota, runner),",
        "  ce n'est pas ton code : reponds verdict=\"blocked\" en le disant ;",
        "- si tu ne peux pas reproduire l'echec localement, dis-le dans `summary` plutot que de",
        "  pousser un correctif a l'aveugle et de laisser la CI trancher a ta place ;",
        "- desactiver, sauter ou rendre tolerant un test qui echoue n'est PAS un correctif. Si le",
        "  test a raison, corrige le code ; s'il a tort, corrige le test et explique pourquoi.",
        "",
        "Tu ne modifies JAMAIS .github/workflows/ : le jeton n'en a pas le droit et le push",
        "serait refuse. Puis commite et pousse.",
    ])


CONFLICT_EXCEPTION = """\
- tu peux lancer `git rebase --continue`, `git merge --continue`, `git add` sur les fichiers
  que tu resous, et `git rebase --abort` si tu renonces. La reecriture d'historique est
  autorisee ICI et nulle part ailleurs, parce que c'est la seule facon de rejouer ta branche
  sur une base qui a bouge ;
- tu ne pousses PAS toi-meme. L'orchestrateur pousse, avec --force-with-lease, et seulement
  apres avoir verifie qu'il ne reste aucun fichier en conflit. Un push force par toi passerait
  a cote de cette verification.
"""


def resolve_conflict_prompt(issue: IssueRef, base: str, method: str,
                            conflicted: tuple[str, ...], landed: tuple[str, ...],
                            attempt: int, max_attempts: int) -> str:
    files = "\n".join(f"- `{path}`" for path in conflicted) or "- (aucun ?)"
    commits = "\n".join(f"- {line}" for line in landed) or "- (inconnu)"
    verb = "rebase" if method.upper() == "REBASE" else "fusion"
    return "\n".join([
        f"PHASE 3c : CONFLIT AVEC `{base}`. Tentative {attempt} sur {max_attempts}.",
        f"Issue {issue.repo}#{issue.number}. Un {verb} de `{base}` sur ta branche est EN COURS",
        "et s'est arrete sur des conflits.",
        "",
        "Fichiers en conflit :",
        files,
        "",
        f"Ce qui a atterri sur `{base}` pendant que tu travaillais, du plus recent au plus ancien :",
        commits,
        "",
        "**La regle qui compte : un conflit se resout en comprenant les DEUX intentions, pas en**",
        "**choisissant un cote.** Pour chaque bloc :",
        "1. lis ce que TON changement voulait faire (ton diff, tes commits, l'issue) ;",
        "2. lis ce que l'AUTRE changement voulait faire (la liste ci-dessus, et `git log -p` sur",
        f"   les commits de `{base}` qui touchent ce fichier) ;",
        "3. ecris la version qui tient les deux. Si elles sont vraiment incompatibles, c'est une",
        "   decision de conception et non un conflit de texte : reponds verdict=\"blocked\" en",
        "   expliquant laquelle des deux intentions doit ceder, et pourquoi.",
        "",
        "⚠ `git checkout --ours` et `--theirs` sont interdits en aveugle. Ils ne resolvent rien :",
        "ils jettent la moitie du travail de quelqu'un, et le resultat compile, donc personne ne le",
        "voit avant que la fonctionnalite perdue ne manque a quelqu'un.",
        "",
        "Quand tout est resolu : `git add` les fichiers, puis termine l'operation",
        f"(`git {'rebase' if method.upper() == 'REBASE' else 'merge'} --continue`).",
        "Verifie ensuite que la suite passe : une resolution qui compile n'est pas une resolution",
        "qui marche, et c'est exactement la classe de bug qu'un conflit produit.",
        "",
        "Dans `summary`, dis pour chaque fichier ce que tu as garde de chaque cote. C'est publie",
        "tel quel sur la pull request : c'est la seule trace que le relecteur aura de ton arbitrage.",
    ])


def wrap_prompt(issue: IssueRef, pr: int) -> str:
    return "\n".join([
        "PHASE 4 sur 4 : CLOTURER. La pull request "
        f"#{pr} a ete APPROUVEE ET FUSIONNEE par l'humain. Le travail est accepte.",
        "",
        "Tu ne modifies plus rien et tu ne pousses plus rien. Deux choses seulement :",
        "- `summary` : ce qui a ete livre, en un paragraphe, tel qu'on l'ecrirait dans un changelog ;",
        "- `followups` : ce que tu as vu passer et qui merite SA PROPRE issue. Rien d'invente pour",
        "  remplir la liste ; une liste vide est une reponse.",
    ])


def _feedback_block(items: tuple[Feedback, ...]) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        where = f" ({item.path}:{item.line})" if item.kind is FeedbackKind.INLINE else ""
        state = f" [{item.state}]" if item.state else ""
        lines.append(f"{index}. @{item.author}{state}{where} :")
        lines.append(_quote(item.body))
    return "\n".join(lines)


def _quote(text: str) -> str:
    return "\n".join(f"  > {line}" for line in text.strip().splitlines() or [""])
