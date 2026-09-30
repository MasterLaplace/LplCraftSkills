#!/usr/bin/env node
'use strict';

const fs = require('node:fs');

const MAP_SKILL = 'cycle-de-dev';
const WRITE_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit', 'MultiEdit']);
const COMMAND_TOOLS = new Set(['Bash', 'PowerShell']);

const ALLOW = 0;
const NOT_CHECKED = 1;
const BLOCK = 2;

function main() {
  const mode = process.argv[2];
  let raw = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { raw += chunk; });
  process.stdin.on('end', () => process.exit(decide(mode, parseInput(raw))));
}

function parseInput(raw) {
  try {
    return JSON.parse(raw || '{}');
  } catch {
    return {};
  }
}

function decide(mode, input) {
  if (mode !== 'pre' && mode !== 'stop') {
    process.stderr.write(`artisan-gate: unknown mode '${mode}'. Expected: pre or stop.\n`);
    return NOT_CHECKED;
  }
  if (mode === 'pre' && !WRITE_TOOLS.has(input.tool_name)) return ALLOW;
  if (mode === 'stop' && input.stop_hook_active) return ALLOW;

  const toolUses = readToolUses(input.transcript_path);
  if (toolUses === null) {
    process.stderr.write(`artisan-gate: transcript not found or unreadable (${input.transcript_path}). `
      + `The '${mode}' rail was not checked for this call.\n`);
    return NOT_CHECKED;
  }
  return mode === 'pre' ? mapLoadedBeforeWriting(toolUses) : provedAfterLastWrite(toolUses);
}

function mapLoadedBeforeWriting(toolUses) {
  const loaded = toolUses.some((use) => use.name === 'Skill' && isMapSkill(use.input && use.input.skill));
  if (loaded) return ALLOW;
  process.stderr.write(`Before writing any file, load the map: Skill tool, skill `
    + `'${MAP_SKILL}'. It says which skill to load at each step of the work. Reading and exploring `
    + `stay allowed without it.\n`);
  return BLOCK;
}

function isMapSkill(name) {
  return typeof name === 'string' && (name === MAP_SKILL || name.endsWith(`:${MAP_SKILL}`));
}

function provedAfterLastWrite(toolUses) {
  const lastWrite = findLastIndex(toolUses, (use) => WRITE_TOOLS.has(use.name));
  if (lastWrite < 0) return ALLOW;
  const lastCommand = findLastIndex(toolUses, (use) => COMMAND_TOOLS.has(use.name));
  if (lastCommand > lastWrite) return ALLOW;
  process.stderr.write(`Files were modified after your last command. Before concluding, `
    + `run right now the command that proves what you are about to claim (tests, build, check), `
    + `then reread the exit gate (the 'porte de sortie' section) of every skill loaded in this session.\n`);
  return BLOCK;
}

function readToolUses(transcriptPath) {
  let text;
  try {
    text = fs.readFileSync(transcriptPath, 'utf8');
  } catch {
    return null;
  }
  const uses = [];
  for (const line of text.split('\n')) {
    if (!line.includes('"tool_use"')) continue;
    let entry;
    try {
      entry = JSON.parse(line);
    } catch {
      continue;
    }
    const content = entry && entry.message && entry.message.content;
    if (!Array.isArray(content)) continue;
    for (const block of content) {
      if (block && block.type === 'tool_use') uses.push({ name: block.name, input: block.input });
    }
  }
  return uses;
}

function findLastIndex(items, predicate) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

main();
