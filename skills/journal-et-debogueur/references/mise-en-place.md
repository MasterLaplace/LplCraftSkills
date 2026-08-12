# Mise en place : les configurations concrètes, par écosystème

Tout ce qui suit est **versionné** : c'est une capacité partagée, pas une préférence. Le critère à tenir
reste le même, **une touche, un point d'arrêt, sans lire de documentation.**

> Les commentaires des blocs de code restent sans accents : ils sont destinés à être copiés dans des
> fichiers de configuration et des sources, où un problème d'encodage coûterait plus que le confort de
> lecture.

## C et C++ : VS Code plus CMake

### `.vscode/tasks.json`, le build que le lancement déclenche

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "cmake-build-debug",
      "type": "shell",
      "command": "cmake --build --preset debug",
      "group": { "kind": "build", "isDefault": true },
      "problemMatcher": ["$gcc"]
    }
  ]
}
```

`problemMatcher` n'est pas cosmétique : c'est ce qui transforme la sortie du compilateur en diagnostics
cliquables. Sans lui, on relit un mur de texte.

### `.vscode/launch.json`, le programme ET le test

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug app (gdb)",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/build/debug/app",
      "args": [],
      "cwd": "${workspaceFolder}",
      "MIMode": "gdb",
      "preLaunchTask": "cmake-build-debug",
      "setupCommands": [
        { "text": "-enable-pretty-printing", "ignoreFailures": true },
        { "text": "set print pretty on", "ignoreFailures": true }
      ]
    },
    {
      "name": "Debug LE test sous le curseur",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/build/debug/tests",
      "args": ["--gtest_filter=${selectedText}*", "--gtest_break_on_failure"],
      "cwd": "${workspaceFolder}",
      "MIMode": "gdb",
      "preLaunchTask": "cmake-build-debug"
    }
  ]
}
```

Sur macOS, remplacer `MIMode` par `lldb` ; sous MSVC, utiliser `"type": "cppvsdbg"` et retirer `MIMode` et
`setupCommands`.

**`--gtest_break_on_failure` est la ligne qui rapporte le plus** : le débogueur s'arrête **sur** l'assertion
qui casse, avec la pile et l'état intacts. Plus rien à reproduire à la main.

### `CMakePresets.json`, quatre presets et chacun répond à un symptôme

```json
{
  "version": 3,
  "configurePresets": [
    {
      "name": "debug", "binaryDir": "${sourceDir}/build/debug",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
    },
    {
      "name": "relwithdebinfo", "binaryDir": "${sourceDir}/build/relwithdebinfo",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo" }
    },
    {
      "name": "asan", "binaryDir": "${sourceDir}/build/asan",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=address,undefined -fno-omit-frame-pointer -g"
      }
    },
    {
      "name": "tsan", "binaryDir": "${sourceDir}/build/tsan",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=thread -g"
      }
    }
  ]
}
```

| Preset | Le symptôme qu'il adresse |
|---|---|
| `debug` | le pas-à-pas ordinaire |
| `relwithdebinfo` | **le bug qui n'existe qu'en release**, et la lecture d'un plantage de production |
| `asan` | corruption, débordement, usage après libération, comportement indéfini |
| `tsan` | course de données. Incompatible avec ASan, donc deux presets et non un |

`RelWithDebInfo` est le preset qu'on oublie et celui qui sert le jour de l'incident. Attention : comme
`Release`, il définit `NDEBUG`, donc les assertions y sont retirées, le décider explicitement, voir la
partie 3 du skill.

### Sanitizers, les options qui changent leur utilité

```bash
export ASAN_OPTIONS=abort_on_error=1:detect_leaks=1:strict_string_checks=1
export UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1
export TSAN_OPTIONS=halt_on_error=1:second_deadlock_stack=1
```

`halt_on_error` et `abort_on_error` : sans eux, le sanitizer **signale et continue**, donc le premier
rapport se noie dans les suivants. `print_stacktrace` pour UBSan : sans lui, on obtient un message sans
lieu, donc une information inutilisable.

### Vidages mémoire, pour le plantage qui n'arrive pas chez toi

```bash
ulimit -c unlimited                                   # Linux, la session en cours
cat /proc/sys/kernel/core_pattern                     # ou vont-ils REELLEMENT
gdb ./build/relwithdebinfo/app core.12345             # ouvrir, avec les symboles
(gdb) bt full                                         # la pile, avec les variables locales
```

Sous Windows : configurer les vidages locaux du rapport d'erreurs (`LocalDumps`, avec un type de vidage
complet), puis ouvrir le fichier dans Visual Studio avec les symboles **de la même version**.

**Conserver les symboles de chaque version livrée.** Un vidage sans ses symboles est illisible, et les
symboles ne se reconstruisent pas à l'identique plus tard.

### `rr` : enregistrement et rejeu à l'envers, sous Linux

```bash
rr record ./build/debug/app --seed 42
rr replay                          # session gdb ordinaire, mais deterministe
(rr) continue                      # jusqu'au plantage
(rr) reverse-continue              # REMONTER dans le temps jusqu'a la cause
(rr) watch -l ptr                  # et remonter jusqu'a QUI a ecrit cette valeur
```

C'est l'outil qui transforme un bug « une fois sur cinquante » en une session unique : on enregistre
jusqu'à l'attraper, puis on rejoue autant qu'on veut sur **la même** exécution.

### `.gdbinit` du projet

```gdb
set print pretty on
set print object on
set pagination off
set history save on
# Afficheurs de la libstdc++ (chemin selon la distribution)
python
import sys; sys.path.insert(0, '/usr/share/gcc/python')
from libstdcxx.v6.printers import register_libstdcxx_printers
register_libstdcxx_printers(None)
end
```

`set pagination off` supprime l'invite de pagination qui bloque tout script. Ajouter `-x` pour le charger,
ou autoriser le fichier local depuis `~/.gdbinit`.

## .NET et C#

```jsonc
// .vscode/launch.json
{
  "name": "Debug CLI",
  "type": "coreclr",
  "request": "launch",
  "program": "${workspaceFolder}/src/App/bin/Debug/net10.0/App.dll",
  "args": ["--verbose"],
  "cwd": "${workspaceFolder}",
  "console": "integratedTerminal",     // sinon l'entree standard ne fonctionne pas
  "preLaunchTask": "build",
  "env": { "Logging__LogLevel__Default": "Debug" }
}
```

```xml
<!-- Directory.Build.props : les symboles SURVIVENT en release -->
<PropertyGroup>
  <DebugType>portable</DebugType>
  <DebugSymbols>true</DebugSymbols>
  <IncludeSymbolsInPackage>true</IncludeSymbolsInPackage>
</PropertyGroup>
```

```bash
dotnet test --filter "FullyQualifiedName~ProratesPartialMonth"   # LE test
dotnet-dump collect -p <pid>        # un vidage a chaud
dotnet-dump analyze core_...        # puis : clrstack, dumpheap -stat
dotnet-trace collect -p <pid>       # la lenteur, pas le debogueur
```

L'extension C# expose « Debug Test » au-dessus de chaque méthode de test : **c'est la configuration sans
friction**, il n'y a rien à écrire.

## Node et TypeScript

```jsonc
// .vscode/launch.json
{
  "name": "Debug vitest (fichier courant)",
  "type": "node",
  "request": "launch",
  "program": "${workspaceFolder}/node_modules/vitest/vitest.mjs",
  "args": ["run", "${relativeFile}", "--no-file-parallelism"],
  "console": "integratedTerminal",
  "smartStep": true,
  "skipFiles": ["<node_internals>/**"]
}
```

`--no-file-parallelism` : sans lui, les processus de travail rendent les points d'arrêt aléatoires.
`skipFiles` évite d'atterrir dans les internes de Node à chaque pas. Les **cartes de source** doivent être
activées dans `tsconfig.json`, sinon le pas-à-pas se fait dans le JavaScript compilé.

## La liste de contrôle du jour 1

- [ ] `launch.json` versionné : **le programme** et **le test sous le curseur**
- [ ] tâche de build câblée au lancement, on ne débogue jamais un binaire périmé
- [ ] un analyseur de sortie de compilation : les erreurs sont cliquables
- [ ] preset `RelWithDebInfo`, et les symboles de release **conservés**
- [ ] preset sanitizer, plus un preset de détection de courses si le projet a des fils d'exécution
- [ ] vidages mémoire activables, et la commande pour les ouvrir **écrite dans le README**
- [ ] journal : niveau modifiable par l'environnement, structuré, et un identifiant de corrélation
- [ ] l'intégration continue construit **Debug ET Release** et joue la suite dans les deux
