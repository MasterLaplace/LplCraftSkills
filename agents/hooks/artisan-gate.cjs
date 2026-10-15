#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const MAP_SKILL = 'cycle-de-dev';
const ANY_SKILL = 'any';
const COMPACTION = 'compaction';
const WRITE_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit', 'MultiEdit']);
const COMMAND_TOOLS = new Set(['Bash', 'PowerShell']);

const ALLOW = 0;
const NOT_CHECKED = 1;
const BLOCK = 2;

function main() {
  const [mode, skillRequirement] = process.argv.slice(2);
  let raw = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { raw += chunk; });
  process.stdin.on('end', () => process.exit(decide(mode, skillRequirement, parseInput(raw))));
}

function parseInput(raw) {
  try {
    return JSON.parse(raw || '{}');
  } catch {
    return {};
  }
}

function decide(mode, skillRequirement, input) {
  if (mode !== 'pre' && mode !== 'stop') {
    process.stderr.write(`artisan-gate: unknown mode '${mode}'. Expected: pre or stop.\n`);
    return NOT_CHECKED;
  }
  if (skillRequirement !== undefined && skillRequirement !== ANY_SKILL) {
    process.stderr.write(`artisan-gate: unknown option '${skillRequirement}'. Expected: nothing (the map) or '${ANY_SKILL}'.\n`);
    return NOT_CHECKED;
  }
  if (mode === 'pre' && !WRITE_TOOLS.has(input.tool_name)) return ALLOW;
  if (mode === 'pre' && isClaudeOwnOrTemporaryFile(writtenPath(input.tool_input))) return ALLOW;
  if (mode === 'stop' && input.stop_hook_active) return ALLOW;

  const timeline = readTimeline(input.transcript_path);
  if (timeline === null) {
    process.stderr.write(`artisan-gate: transcript not found or unreadable (${input.transcript_path}). `
      + `The '${mode}' rail was not checked for this call.\n`);
    return NOT_CHECKED;
  }
  return mode === 'pre' ? skillLoadedBeforeWriting(timeline, skillRequirement) : provedAfterLastWrite(timeline);
}

function skillLoadedBeforeWriting(timeline, skillRequirement) {
  const lastCompaction = findLastIndex(timeline, (use) => use.name === COMPACTION);
  const accepts = skillRequirement === ANY_SKILL ? () => true : isMapSkill;
  const loaded = timeline.slice(lastCompaction + 1).some((use) => use.name === 'Skill' && accepts(use.input && use.input.skill));
  if (loaded) return ALLOW;
  const sinceCompaction = lastCompaction < 0 ? '' : ' since the last compaction, which may have dropped it';
  if (skillRequirement === ANY_SKILL) {
    process.stderr.write(`Before writing any file, load the skill of the step you are at (Skill tool): none was `
      + `loaded${sinceCompaction}. The map '${MAP_SKILL}' says which one. Reading and exploring stay allowed without it.\n`);
  } else {
    process.stderr.write(`Before writing any file, load the map: Skill tool, skill '${MAP_SKILL}', not loaded`
      + `${sinceCompaction}. It says which skill to load at each step of the work. Reading and exploring stay allowed `
      + `without it.\n`);
  }
  return BLOCK;
}

function isMapSkill(name) {
  return typeof name === 'string' && (name === MAP_SKILL || name.endsWith(`:${MAP_SKILL}`));
}

function writtenPath(toolInput) {
  return toolInput && (toolInput.file_path || toolInput.notebook_path);
}

function isClaudeOwnOrTemporaryFile(filePath) {
  if (typeof filePath !== 'string') return false;
  const target = comparable(filePath);
  return [path.join(os.homedir(), '.claude'), os.tmpdir()]
    .some((folder) => target.startsWith(comparable(folder) + path.sep));
}

function comparable(somePath) {
  const resolved = realPath(path.resolve(somePath));
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}

function realPath(somePath) {
  try {
    return fs.realpathSync.native(somePath);
  } catch {
    const parent = path.dirname(somePath);
    return parent === somePath ? somePath : path.join(realPath(parent), path.basename(somePath));
  }
}

function provedAfterLastWrite(timeline) {
  const lastWrite = findLastIndex(timeline, (use) => WRITE_TOOLS.has(use.name));
  if (lastWrite < 0) return ALLOW;
  const lastCommand = findLastIndex(timeline, (use) => COMMAND_TOOLS.has(use.name));
  if (lastCommand > lastWrite) return ALLOW;
  process.stderr.write(`Files were modified after your last command. Before concluding, `
    + `run right now the command that proves what you are about to claim (tests, build, check), `
    + `then reread the exit gate (the 'porte de sortie' section) of every skill loaded in this session.\n`);
  return BLOCK;
}

function readTimeline(transcriptPath) {
  let text;
  try {
    text = fs.readFileSync(transcriptPath, 'utf8');
  } catch {
    return null;
  }
  const timeline = [];
  const seenEntries = new Set();
  for (const line of text.split('\n')) {
    if (!line.includes('"tool_use"') && !line.includes('"isCompactSummary"')) continue;
    let entry;
    try {
      entry = JSON.parse(line);
    } catch {
      continue;
    }
    if (!entry || seenEntries.has(entry.uuid)) continue;
    if (entry.uuid) seenEntries.add(entry.uuid);
    if (entry.isCompactSummary) {
      timeline.push({ name: COMPACTION });
      continue;
    }
    const content = entry.message && entry.message.content;
    if (!Array.isArray(content)) continue;
    for (const block of content) {
      if (block && block.type === 'tool_use') timeline.push({ name: block.name, input: block.input });
    }
  }
  return timeline;
}

function findLastIndex(items, predicate) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

main();
