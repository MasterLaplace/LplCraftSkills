# La doc de contrat, par langage

Même rôle partout : **décrire un contrat à quelqu'un qui n'ouvrira pas le code.** Trois questions, jamais
une quatrième, ce que ça **garantit**, ce que ça **exige**, ce que ça **peut lever**. Le *comment* n'y
figure jamais : il est dans le corps, et il changera.

**Sur la frontière publique uniquement.** Une doc de contrat sur une fonction privée est un duplicata de
plus à maintenir, sans lecteur.

## C et C++ : Doxygen

Le langage où la doc de contrat rapporte le plus, parce que le type dit le moins : propriétaire de la
mémoire, durée de vie, alignement, réentrance, aucun de ces contrats n'est dans la signature.

```c
/**
 * @brief Lit au plus @p capacity octets depuis @p fd dans @p buffer.
 *
 * @param fd Descripteur ouvert en lecture. Reste la propriete de l'appelant.
 * @param buffer Tampon d'au moins @p capacity octets, alloue par l'appelant.
 * @param capacity Taille du tampon, en octets. Doit etre > 0.
 * @return Nombre d'octets lus, ou -1 en cas d'erreur (errno est positionne).
 * @retval 0 Fin de fichier.
 * @warning Non reentrante : utilise un tampon statique interne.
 * @note Reprend sur EINTR ; l'appelant n'a pas a boucler.
 */
ssize_t read_chunk(int fd, char *buffer, size_t capacity);
```

Les balises qui portent vraiment quelque chose en C et C++ : `@param` avec **qui possède** le pointeur,
`@return` et `@retval`, `@pre` et `@post`, `@throws` en C++, `@warning` pour la réentrance et la sûreté
entre fils d'exécution, `@note` pour le pourquoi non déductible. Le `@brief` tient sur une ligne, à
l'impératif.

**Ce qui ne doit PAS y être** : la complexité algorithmique si elle n'est pas garantie, puisqu'elle
changera, et une description du corps.

## Assembleur

Le seul endroit où le commentaire de ligne est **la norme et non une odeur** : l'intention n'est nulle part
dans le code, et le lecteur ne peut pas la reconstruire.

```asm
; compute_checksum(rdi = buffer, rsi = length) -> rax
; Clobbers: rcx, rdx. Preserves: rbx, rbp, r12-r15 (System V AMD64).
; Requiert length > 0 ; le cas nul est filtre par l'appelant.
compute_checksum:
    xor     rax, rax            ; accumulateur = 0
    mov     rcx, rsi            ; compteur = length
.loop:
    add     al, [rdi + rcx - 1] ; somme non signee, repliement volontaire sur 8 bits
    loop    .loop
    ret
```

Ce qu'un en-tête de routine doit dire, et que rien d'autre ne peut dire : la **convention d'appel**, les
registres **écrasés** et **préservés**, les conditions d'entrée, les effets mémoire.

## C# : commentaires de documentation XML

```csharp
/// <summary>Calcule le montant proratise pour un mois partiel.</summary>
/// <param name="contract">Contrat actif ; <paramref name="period"/> doit tenir dans sa validite.</param>
/// <param name="period">Plage fermee, exprimee en jours ouvres.</param>
/// <returns>Montant en centimes, arrondi au centime superieur.</returns>
/// <exception cref="ArgumentOutOfRangeException">
/// La periode sort de la validite du contrat.
/// </exception>
/// <remarks>
/// L'arrondi superieur est impose par la convention collective, pas par un choix technique.
/// </remarks>
public static Money ComputeProratedAmount(Contract contract, DateRange period)
```

`<exception>` est la balise à ne jamais sauter : c'est la seule partie du contrat qui n'apparaît **nulle
part** dans la signature en C#. Activer la génération du fichier de documentation pour que l'absence de doc
sur du public devienne un avertissement du compilateur, **dériver plutôt que discipliner**.

## TypeScript : TSDoc

```ts
/**
 * Calcule le montant proratise pour un mois partiel.
 *
 * @param contract - Contrat actif ; `period` doit tenir dans sa validite.
 * @param period - Plage fermee, en jours ouvres.
 * @returns Montant en centimes, arrondi au centime superieur.
 * @throws {@link OutOfContractRangeError} Si la periode sort de la validite.
 *
 * @remarks
 * L'arrondi superieur est impose par la convention collective.
 */
export function computeProratedAmount(contract: Contract, period: DateRange): Money
```

En TypeScript, **le type porte déjà la moitié du contrat** : ne jamais redire dans la doc ce que la
signature dit, `@param contract - le contrat` est du bruit. Ce qui reste à écrire : les **unités**, les
**plages valides**, les **erreurs**, les **effets de bord**, et le pourquoi.

## Rust : rustdoc

```rust
/// Calcule le montant proratise pour un mois partiel.
///
/// # Errors
/// Retourne [`BillingError::OutOfContractRange`] si `period` sort de la validite.
///
/// # Panics
/// Panique si `period` est inversee (invariant garanti par [`DateRange::new`]).
///
/// # Examples
/// ```
/// let amount = compute_prorated_amount(&contract, period)?;
/// assert_eq!(amount.cents(), 600);
/// ```
pub fn compute_prorated_amount(contract: &Contract, period: DateRange) -> Result<Money, BillingError>
```

Le seul écosystème où l'exemple de doc est **exécuté par les tests** : c'est de la dérivation native,
l'exemple ne peut pas mentir longtemps. Les sections `# Errors`, `# Panics` et `# Safety`, pour le code
non sûr, sont attendues par convention.

## Python : docstrings

```python
def compute_prorated_amount(contract: Contract, period: DateRange) -> Money:
    """Calcule le montant proratise pour un mois partiel.

    Args:
        contract: Contrat actif ; `period` doit tenir dans sa validite.
        period: Plage fermee, en jours ouvres.

    Returns:
        Montant en centimes, arrondi au centime superieur.

    Raises:
        OutOfContractRangeError: La periode sort de la validite du contrat.
    """
```

`Raises` est la section la plus souvent omise et la plus utile : en Python, rien dans la signature ne
l'annonce.

## Le tableau de correspondance

| Langage | Outil | La balise à ne jamais sauter | Ce que le langage ne dit pas tout seul |
|---|---|---|---|
| C | Doxygen | `@param` plus la propriété du pointeur | durée de vie, réentrance, code d'erreur système |
| C++ | Doxygen | `@throws`, `@pre` | propriétaire, sûreté face aux exceptions, invalidation d'itérateur |
| Assembleur | commentaire de ligne | l'en-tête de routine | convention d'appel, registres écrasés |
| C# | doc XML | `<exception>` | ce qui est levé |
| TypeScript | TSDoc | `@throws`, les unités | effets de bord, plages valides |
| Rust | rustdoc | `# Errors`, `# Panics`, `# Safety` | conditions de panique |
| Python | docstring | `Raises`, les types | à peu près tout, d'où les annotations |

## Et la règle qui vaut plus que le format

**Ce qui peut être dérivé ne doit pas être écrit.** Un exemple exécuté, un avertissement de compilateur sur
du public non documenté, une doc générée depuis les signatures : tous coûtent moins cher qu'une relecture,
et surtout **ils cassent quand ils mentent**. Ce qui reste écrit à la main doit être apparié par un test, ou
assumé par écrit comme pouvant dériver.
