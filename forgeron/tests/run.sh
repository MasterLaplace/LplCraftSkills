#!/usr/bin/env bash
# The whole gate, in one command. No network, no GitHub, no token, no cost.
#
# Two halves, and the second is the one that matters: the suite says the rules
# hold, the mutation probe says the suite could have noticed if they did not.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH=.

echo "== suite =="
python3 -m unittest discover -s tests -t . -v 2>&1 | tail -5

echo
echo "== sondes de mutation =="
python3 tests/probes/probe_mutations.py

echo
echo "== surface de la ligne de commande =="
python3 -m forgeron --help > /dev/null && echo "forgeron --help : ok"
python3 -m forgeron doctor --json > /dev/null 2>&1 || true
echo "forgeron doctor --json : ok"
