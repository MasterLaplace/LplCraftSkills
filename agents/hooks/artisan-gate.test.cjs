'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const GATE = path.join(__dirname, 'artisan-gate.cjs');

let entryCount = 0;
const uuid = () => `00000000-0000-4000-8000-${String((entryCount += 1)).padStart(12, '0')}`;
function toolUse(name, input) {
  return { type: 'assistant', isSidechain: false, uuid: uuid(),
           message: { role: 'assistant', content: [{ type: 'tool_use', id: 'x', name, input }] } };
}
const userText = (text) => ({ type: 'user', message: { role: 'user', content: text } });
const compaction = () => ({ type: 'user', uuid: uuid(), isVisibleInTranscriptOnly: true, isCompactSummary: true,
                            message: { role: 'user', content: 'This session is being continued from a previous conversation.' } });
const loadMap = () => toolUse('Skill', { skill: 'cycle-de-dev' });
const write = () => toolUse('Write', { file_path: 'a.txt', content: 'x' });
const edit = () => toolUse('Edit', { file_path: 'a.txt', old_string: 'x', new_string: 'y' });
const bash = () => toolUse('Bash', { command: 'npm test' });
const powershell = () => toolUse('PowerShell', { command: 'dotnet test' });

function transcript(entries, { garbage = false } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'artisan-gate-'));
  const file = path.join(dir, 'session.jsonl');
  const lines = entries.map((entry) => JSON.stringify(entry));
  if (garbage) lines.splice(1, 0, '{ this is not json');
  fs.writeFileSync(file, lines.join('\n') + '\n');
  return file;
}

function runIn(environment, mode, input, ...options) {
  const done = spawnSync(process.execPath, [GATE, mode, ...options],
                         { input: JSON.stringify(input), encoding: 'utf8', env: { ...process.env, ...environment } });
  return { code: done.status, stderr: done.stderr };
}
const run = (mode, input, ...options) => runIn({}, mode, input, ...options);


test('a write without the map loaded is blocked, and the message names the skill', () => {
  const file = transcript([userText('add X'), bash()]);
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: file });
  assert.equal(code, 2);
  assert.match(stderr, /cycle-de-dev/);
  assert.match(stderr, /Skill/);
});

test('Edit is a write like Write', () => {
  const file = transcript([userText('fix Y')]);
  assert.equal(run('pre', { tool_name: 'Edit', transcript_path: file }).code, 2);
});

test('a write after the map is loaded passes', () => {
  const file = transcript([userText('add X'), loadMap(), bash()]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('reading does not require the map: exploring comes first', () => {
  const file = transcript([userText('add X')]);
  for (const tool of ['Read', 'Grep', 'Glob', 'Bash']) {
    assert.equal(run('pre', { tool_name: tool, transcript_path: file }).code, 0, tool);
  }
});

test('a skill from a plugin, prefixed by its namespace, counts too', () => {
  const file = transcript([toolUse('Skill', { skill: 'craft:cycle-de-dev' })]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('ANOTHER skill does not replace the map', () => {
  const file = transcript([toolUse('Skill', { skill: 'tests-first' })]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 2);
});

test('after a compaction, the map loaded before it no longer counts', () => {
  const file = transcript([loadMap(), compaction(), userText('go on')]);
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: file });
  assert.equal(code, 2);
  assert.match(stderr, /compaction/);
});

test('after a compaction, loading the map again lets the write pass', () => {
  const file = transcript([loadMap(), compaction(), loadMap()]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('a map call replayed after the compaction is not a new load', () => {
  const map = loadMap();
  const file = transcript([map, compaction(), map]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 2);
});

test('a compaction replayed after the map was loaded again does not block again', () => {
  const summary = compaction();
  const file = transcript([loadMap(), summary, loadMap(), summary]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('with the any option, any skill loaded since the last compaction lets the write pass', () => {
  const file = transcript([compaction(), toolUse('Skill', { skill: 'tests-first' })]);
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }, 'any').code, 0);
});

test('with the any option, no skill since the last compaction blocks the write, and says so', () => {
  const file = transcript([toolUse('Skill', { skill: 'tests-first' }), compaction()]);
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: file }, 'any');
  assert.equal(code, 2);
  assert.match(stderr, /skill/);
  assert.match(stderr, /compaction/);
});

test('an unknown option is a calling error, not a silent change of rule', () => {
  const file = transcript([loadMap()]);
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: file }, 'anyy');
  assert.equal(code, 1);
  assert.match(stderr, /anyy/);
  assert.match(stderr, /any/);
});

test("Claude's own files and the temporary folder are written without the map", () => {
  const file = transcript([userText('remember this')]);
  for (const filePath of [path.join(os.homedir(), '.claude', 'projects', 'p', 'memory', 'note.md'),
                          path.join(os.tmpdir(), 'scratchpad', 'probe.cjs')]) {
    assert.equal(run('pre', { tool_name: 'Write', tool_input: { file_path: filePath }, transcript_path: file }).code, 0, filePath);
  }
});

test('a notebook in the temporary folder is written without the map', () => {
  const file = transcript([userText('try something')]);
  const notebook = path.join(os.tmpdir(), 'scratchpad', 'probe.ipynb');
  assert.equal(run('pre', { tool_name: 'NotebookEdit', tool_input: { notebook_path: notebook }, transcript_path: file }).code, 0);
});

test('a link under ~/.claude that leads into a repository still needs the map', () => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'artisan-gate-home-'));
  const home = path.join(sandbox, 'home');
  const temporary = path.join(sandbox, 'temp');
  const repository = path.join(sandbox, 'repository');
  for (const folder of [path.join(home, '.claude', 'skills'), temporary, repository]) fs.mkdirSync(folder, { recursive: true });
  fs.symlinkSync(repository, path.join(home, '.claude', 'skills', 'linked'), 'junction');
  const file = transcript([userText('edit the skill')]);
  const environment = { HOME: home, USERPROFILE: home, TEMP: temporary, TMP: temporary, TMPDIR: temporary };
  const filePath = path.join(home, '.claude', 'skills', 'linked', 'SKILL.md');
  assert.equal(runIn(environment, 'pre', { tool_name: 'Write', tool_input: { file_path: filePath }, transcript_path: file }).code, 2);
});

test('a file of a repository still needs the map, even next to those folders', () => {
  const file = transcript([userText('add X')]);
  for (const filePath of [path.join(os.homedir(), 'repo', 'a.txt'), path.join(os.homedir(), '.claude-other', 'a.txt')]) {
    assert.equal(run('pre', { tool_name: 'Write', tool_input: { file_path: filePath }, transcript_path: file }).code, 2, filePath);
  }
});

test('an unreadable line in the transcript is skipped, not fatal', () => {
  const file = transcript([userText('x'), loadMap()], { garbage: true });
  assert.equal(run('pre', { tool_name: 'Write', transcript_path: file }).code, 0);
});

test('a transcript that cannot be found gives a LOUD, non-blocking error', () => {
  const { code, stderr } = run('pre', { tool_name: 'Write', transcript_path: '/nowhere/at-all/session.jsonl' });
  assert.equal(code, 1);
  assert.match(stderr, /not found|unreadable/);
  assert.match(stderr, /\/nowhere\/at-all\/session\.jsonl/);
});


test('modifying a file after the last command blocks the stop', () => {
  const file = transcript([loadMap(), bash(), edit()]);
  const { code, stderr } = run('stop', { stop_hook_active: false, transcript_path: file });
  assert.equal(code, 2);
  assert.match(stderr, /command/);
  assert.match(stderr, /exit gate/);
});

test('a command after the last write lets the session stop', () => {
  const file = transcript([loadMap(), write(), bash()]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('PowerShell counts as a command, just like Bash', () => {
  const file = transcript([loadMap(), write(), powershell()]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('a session without any write stops freely', () => {
  const file = transcript([userText('explain X to me'), toolUse('Read', { file_path: 'a' })]);
  assert.equal(run('stop', { stop_hook_active: false, transcript_path: file }).code, 0);
});

test('the second stop always passes: the hook sends back once, never in a loop', () => {
  const file = transcript([loadMap(), bash(), edit()]);
  assert.equal(run('stop', { stop_hook_active: true, transcript_path: file }).code, 0);
});

test('a transcript that cannot be found at stop gives a loud, non-blocking error', () => {
  const { code } = run('stop', { stop_hook_active: false, transcript_path: '/nowhere/at-all/s.jsonl' });
  assert.equal(code, 1);
});

test('an unknown mode is a calling error, not a silent pass', () => {
  const file = transcript([]);
  const { code, stderr } = run('elsewhere', { transcript_path: file });
  assert.equal(code, 1);
  assert.match(stderr, /pre|stop/);
});
