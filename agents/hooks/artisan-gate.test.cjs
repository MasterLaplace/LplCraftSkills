'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const GATE = path.join(__dirname, 'artisan-gate.cjs');

function toolUse(name, input) {
  return { type: 'assistant', isSidechain: false,
           message: { role: 'assistant', content: [{ type: 'tool_use', id: 'x', name, input }] } };
}
const userText = (text) => ({ type: 'user', message: { role: 'user', content: text } });
const loadMap = () => toolUse('Skill', { skill: 'cycle-de-dev' });
const write = () => toolUse('Write', { file_path: 'a.txt', content: 'x' });
const edit = () => toolUse('Edit', { file_path: 'a.txt', old_string: 'x', new_string: 'y' });
const bash = () => toolUse('Bash', { command: 'npm test' });
const powershell = () => toolUse('PowerShell', { command: 'dotnet test' });

function transcript(entries, { garbage = false } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'artisan-gate-'));
  const file = path.join(dir, 'session.jsonl');
  const lines = entries.map((entry) => JSON.stringify(entry));
  if (garbage) lines.splice(1, 0, '{ ceci nest pas du json');
  fs.writeFileSync(file, lines.join('\n') + '\n');
  return file;
}

function run(mode, input) {
  const done = spawnSync(process.execPath, [GATE, mode], { input: JSON.stringify(input), encoding: 'utf8' });
  return { code: done.status, stderr: done.stderr };
}


test('une ecriture sans la carte chargee est bloquee, et le message nomme le skill', () => {
  const file = transcript([userText('ajoute X'), bash()]);
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: file });
  assert.equal(code, 2);
  assert.match(stderr, /cycle-de-dev/);
  assert.match(stderr, /Skill/);
});

test('Edit est une ecriture comme Write', () => {
  const file = transcript([userText('corrige Y')]);
  assert.equal(run('pre', { tool_name: 'Edit', transcript_path: file }).code, 2);
});

test('une ecriture apres le chargement de la carte passe', () => {
  const file = transcript([userText('ajoute X'), loadMap(), bash()]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('lire ne demande pas la carte : explorer vient avant', () => {
  const file = transcript([userText('ajoute X')]);
  for (const tool of ['Read', 'Grep', 'Glob', 'Bash']) {
    assert.equal(run('pre', { tool_name: tool, transcript_path: file }).code, 0, tool);
  }
});

test('un skill venu d un greffon, prefixe par son espace de noms, compte aussi', () => {
  const file = transcript([toolUse('Skill', { skill: 'craft:cycle-de-dev' })]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('un AUTRE skill ne remplace pas la carte', () => {
  const file = transcript([toolUse('Skill', { skill: 'tests-first' })]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 2);
});

test('une ligne illisible dans le transcript est sautee, pas fatale', () => {
  const file = transcript([userText('x'), loadMap()], { garbage: true });
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('un transcript introuvable donne une erreur BRUYANTE et non bloquante', () => {
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: '/nulle/part/session.jsonl' });
  assert.equal(code, 1);
  assert.match(stderr, /introuvable|illisible/);
  assert.match(stderr, /\/nulle\/part\/session\.jsonl/);
});


test('modifier un fichier apres la derniere commande bloque l arret', () => {
  const file = transcript([loadMap(), bash(), edit()]);
  const { code, stderr } = run('stop', { stop_hook_active: false, transcript_path: file });
  assert.equal(code, 2);
  assert.match(stderr, /commande/);
  assert.match(stderr, /porte de sortie/);
});

test('une commande apres la derniere ecriture laisse s arreter', () => {
  const file = transcript([loadMap(), write(), bash()]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('PowerShell compte comme une commande, au meme titre que Bash', () => {
  const file = transcript([loadMap(), write(), powershell()]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('une session sans aucune ecriture s arrete librement', () => {
  const file = transcript([userText('explique-moi X'), toolUse('Read', { file_path: 'a' })]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('le deuxieme arret passe toujours : le hook relance une fois, jamais en boucle', () => {
  const file = transcript([loadMap(), bash(), edit()]);
  assert.equal(run('stop', { stop_hook_active: true, transcript_path: file }).code, 0);
});

test('un transcript introuvable a l arret donne une erreur bruyante et non bloquante', () => {
  const { code } = run('stop', { stop_hook_active: false, transcript_path: '/nulle/part/s.jsonl' });
  assert.equal(code, 1);
});

test('un mode inconnu est une erreur d appel, pas un laisser-passer silencieux', () => {
  const file = transcript([]);
  const { code, stderr } = run('ailleurs', { transcript_path: file });
  assert.equal(code, 1);
  assert.match(stderr, /pre|stop/);
});
