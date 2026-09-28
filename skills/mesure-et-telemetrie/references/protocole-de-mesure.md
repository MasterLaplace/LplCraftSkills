# Protocole de mesure : la liste de contrôle et les commandes

Une mesure qui ne dit pas **dans quelles conditions** elle a été prise n'est pas reproductible, donc ce
n'est pas une mesure. Ce fichier tient le protocole minimal et les commandes par écosystème.

> Les commentaires des blocs de code restent sans accents : ils sont destinés à être copiés dans des
> scripts et des sources.

## La liste de contrôle, avant de publier un chiffre

- [ ] **itérations de chauffe** jetées : cache, compilation à la volée, contexte GPU, allocateur
- [ ] **N tirages**, avec la **variance** et le **nombre de tirages** publiés
- [ ] **médiane et p95 ou p99**, jamais une moyenne seule
- [ ] **cœur épinglé**, gouverneur de fréquence fixe, machine au repos
- [ ] **A et B entrelacés** (A, B, A, B...) et non tous les A puis tous les B
- [ ] **état de l'arbre enregistré** avec la mesure : commit, modifications non commitées, empreinte
- [ ] le résultat n'est **pas trop beau**, un ordre de grandeur inattendu est un bug de banc
- [ ] la **taille d'entrée varie** : un temps insensible à l'entrée ne mesure rien
- [ ] un **test de correction** couvre le même code

## Linux : réduire le bruit

```bash
# Epingler sur un coeur, priorite haute
taskset -c 3 chrt -f 99 ./build/relwithdebinfo/bench

# Gouverneur en performance (supprime la montee et la descente de frequence)
sudo cpupower frequency-set -g performance
# Desactiver le turbo : la frequence cesse de deriver avec la temperature
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo

# Etat REEL apres coup -- ne jamais supposer ce qu'on a demande
cpupower frequency-info | head -20
grep MHz /proc/cpuinfo | sort -u

# Desactiver la randomisation d'adresses pour une mesure comparable a l'octet
setarch $(uname -m) -R ./bench
```

**Vérifier après, pas seulement demander** : un gouverneur est refusé en silence sur certaines machines
virtuelles, et un bridage thermique ne s'annonce pas.

## Temps de bout en bout : `hyperfine`

```bash
hyperfine --warmup 3 --runs 20 \
  --export-json .tmp/bench.json \
  './build/a/app --input large' './build/b/app --input large'
```

Il fait la chauffe, les tirages, l'écart-type et la comparaison relative. Pour de l'A/B, c'est le moyen le
plus court d'obtenir une distribution au lieu d'un nombre.

## Compteurs matériels : `perf`

```bash
# Ce qui distingue "devenu memoire" de "devenu algorithme"
perf stat -e instructions,cycles,cache-misses,cache-references,branch-misses ./bench

# Ou passe le temps, par fonction puis par ligne
perf record -g --call-graph dwarf ./bench && perf report
perf annotate -s ComputeChecksum
```

Les deux rapports qui parlent : **instructions par cycle**, un ratio bas veut dire qu'on attend la mémoire
, et le **taux de défauts de cache**. Un temps qui double à instructions constantes se lit directement ici.

## Comptage d'instructions pour l'intégration continue

```bash
valgrind --tool=cachegrind --cache-sim=yes ./bench 2> .tmp/cg.txt
grep -E '^(I refs|D1  misses|LLd misses)' .tmp/cg.txt

# Alternative legere, sans valgrind
perf stat -e instructions -x, ./bench 2>&1 | cut -d, -f1
```

C'est ce qui permet un seuil serré sur un exécuteur partagé : la variance du **temps** y est de 20 à 50 %,
celle des **instructions** est de l'ordre du pour-mille. Ça ne mesure pas la latence, et ce n'est pas ce
qu'on lui demande.

## C++ : Google Benchmark

```cpp
static void BM_ComputeChecksum(benchmark::State &state)
{
    const std::vector<char> buffer(state.range(0), 'x');
    for (auto _ : state) {
        auto value = ComputeChecksum(buffer);
        benchmark::DoNotOptimize(value);   // sinon le calcul est supprime
    }
    state.SetBytesProcessed(state.iterations() * state.range(0));  // normalise
}
BENCHMARK(BM_ComputeChecksum)->Range(1 << 10, 1 << 24);   // fait varier la taille
```

```bash
./bench --benchmark_repetitions=20 --benchmark_report_aggregates_only=true \
        --benchmark_out=.tmp/bench.json --benchmark_out_format=json
```

`Range` est ce qui rend le banc **diagnostique** : la courbe montre le décrochage quand un niveau de cache
déborde, ce qu'un point unique ne peut pas montrer.

## CUDA : mesurer le noyau, pas la mise en file

```cpp
cudaEvent_t start, stop;
cudaEventCreate(&start); cudaEventCreate(&stop);

LaunchKernel<<<grid, block>>>(device_input, device_output);   // CHAUFFE, jetee
cudaDeviceSynchronize();

cudaEventRecord(start);
LaunchKernel<<<grid, block>>>(device_input, device_output);
cudaEventRecord(stop);
cudaEventSynchronize(stop);

float elapsed_ms = 0.0F;
cudaEventElapsedTime(&elapsed_ms, start, stop);   // temps PERIPHERIQUE du noyau seul
```

```bash
# Chronologie complete : transferts, noyaux, et les TROUS entre les deux
nsys profile --stats=true -o .tmp/timeline ./app

# Compteurs d'un noyau : bande passante atteinte contre crete, occupation, goulot
ncu --set full --kernel-name LaunchKernel -o .tmp/kernel ./app
ncu --metrics dram__throughput.avg.pct_of_peak_sustained_elapsed ./app
```

Compiler avec `-lineinfo` : le profil se corrèle au source, sans coût en performance. Publier **trois
nombres** (hôte vers périphérique, calcul, périphérique vers hôte), jamais leur somme seule.

## .NET : BenchmarkDotNet

```csharp
[MemoryDiagnoser]                       // allocations : souvent la vraie cause
[SimpleJob(RuntimeMoniker.Net10_0)]
public class ProrationBenchmarks
{
    [Params(100, 10_000, 1_000_000)]    // fait varier la taille
    public int ContractCount;

    [Benchmark(Baseline = true)] public Money Current() => ComputeAll(_contracts);
    [Benchmark] public Money Candidate() => ComputeAllFast(_contracts);
}
```

```bash
dotnet run -c Release -- --filter '*Proration*' --exporters json
dotnet-counters monitor -p <pid>      # en production : GC, files d'attente, exceptions
```

Il gère chauffe, tirages, distribution, ratio contre la ligne de base et allocations. **Jamais en Debug** :
il refuse, et c'est bien.

## Node et TypeScript

```bash
vitest bench --run                    # ou mitata pour du micro-banc
node --cpu-prof --cpu-prof-dir=.tmp/prof app.js   # profil V8
node --heap-prof app.js               # allocations
```

## Le script A/B entrelacé, forme minimale

```bash
#!/usr/bin/env bash
# Entrelace deux binaires pour neutraliser la derive thermique et la charge de fond.
set -euo pipefail
OUT=/c/Code/.tmp/ab.csv          # chemin ABSOLU
echo "run,arm,ms" > "$OUT"
for i in $(seq 1 15); do
  for arm in a b; do
    ms=$( { /usr/bin/time -f %e "./build/$arm/app" --input large >/dev/null; } 2>&1 )
    echo "$i,$arm,$ms" >> "$OUT"
  done
done
# Enregistrer l'etat de l'arbre AVEC la mesure, sinon les deux bras sont incomparables
git rev-parse HEAD >> "$OUT.tree"; git diff --stat >> "$OUT.tree"
```

## Les contrôles de vraisemblance

| Signe | Ce que c'est presque toujours |
|---|---|
| un gain d'un ordre de grandeur inattendu | le calcul a été supprimé, ou on mesure une mise en file |
| un temps insensible à la taille d'entrée | on ne mesure pas le code visé |
| un écart qui disparaît en changeant l'ordre des bras | de la dérive, pas un effet |
| une variance supérieure à l'écart mesuré | il n'y a **pas** d'écart mesurable : dire « non concluant » |

La dernière ligne est la plus importante : **« non concluant » est un résultat**, et le publier vaut mieux
que de trancher sur du bruit.
