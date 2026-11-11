#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { WRITE_TOOLS, missingStepSkills, isSkillNamed, isClaudeOwnOrTemporaryFile } = require('./write-rules.cjs');

const MAP_SKILL = 'cycle-de-dev';
const ANY_SKILL = 'any';
const COMPACTION = 'compaction';
const COMMAND_TOOLS = new Set(['Bash', 'PowerShell']);
const CHUNK_BYTES = 4 * 1024 * 1024;
const LONGEST_LINE_BYTES = 64 * 1024 * 1024;
const NEWLINE = 0x0a;
const TOOL_USE_MARK = Buffer.from('"tool_use"');
const COMPACTION_MARK = Buffer.from('"isCompactSummary"');

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
  return mode === 'pre'
    ? skillLoadedBeforeWriting(timeline, skillRequirement, writtenPath(input.tool_input), Boolean(input.agent_id))
    : provedAfterLastWrite(timeline);
}

function skillLoadedBeforeWriting(timeline, skillRequirement, filePath, writtenBySubagent) {
  const lastCompaction = findLastIndex(timeline, (use) => use.name === COMPACTION);
  const loadedSkills = skillsLoadedAfter(timeline, lastCompaction);
  const generalRuleMet = skillRequirement === ANY_SKILL
    ? loadedSkills.length > 0
    : loadedSkills.some((name) => isSkillNamed(name, MAP_SKILL));
  if (!generalRuleMet) {
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

  if (writtenBySubagent) return ALLOW;
  const stepOfWrite = missingStepSkills(filePath, loadedSkills);
  if (stepOfWrite === null || stepOfWrite.missingSkills.length === 0) return ALLOW;
  const { step, missingSkills } = stepOfWrite;
  const notLoaded = lastCompaction < 0
    ? 'not loaded in this session'
    : `not loaded since the last compaction, which may have dropped ${missingSkills.length > 1 ? 'them' : 'it'}`;
  process.stderr.write(`Before writing ${path.basename(filePath)}, a file of the '${step}' step of '${MAP_SKILL}', load `
    + `what that step names (Skill tool): ${missingSkills.join(', ')}, ${notLoaded}. Reading and exploring stay allowed `
    + `without ${missingSkills.length > 1 ? 'them' : 'it'}.\n`);
  return BLOCK;
}

function skillsLoadedAfter(timeline, index) {
  return timeline.slice(index + 1)
    .filter((use) => use.name === 'Skill' && use.input && typeof use.input.skill === 'string')
    .map((use) => use.input.skill);
}

function writtenPath(toolInput) {
  return toolInput && (toolInput.file_path || toolInput.notebook_path);
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
  let descriptor;
  try {
    descriptor = fs.openSync(transcriptPath, 'r');
  } catch {
    return null;
  }
  const timeline = [];
  const seenEntries = new Set();
  try {
    forEachLine(descriptor, (line) => addToTimeline(timeline, seenEntries, line));
  } catch {
    return null;
  } finally {
    fs.closeSync(descriptor);
  }
  return timeline;
}

function forEachLine(descriptor, onLine) {
  const chunk = Buffer.alloc(CHUNK_BYTES);
  let pieces = [];
  let piecesBytes = 0;
  let insideOversizedLine = false;
  for (let read = fs.readSync(descriptor, chunk, 0, CHUNK_BYTES, null); read > 0;
    read = fs.readSync(descriptor, chunk, 0, CHUNK_BYTES, null)) {
    const data = chunk.subarray(0, read);
    let lineStart = 0;
    for (let newline = data.indexOf(NEWLINE); newline >= 0; newline = data.indexOf(NEWLINE, lineStart)) {
      if (!insideOversizedLine) onLine(Buffer.concat([...pieces, data.subarray(lineStart, newline)]));
      pieces = [];
      piecesBytes = 0;
      insideOversizedLine = false;
      lineStart = newline + 1;
    }
    const rest = data.subarray(lineStart);
    insideOversizedLine = insideOversizedLine || piecesBytes + rest.length > LONGEST_LINE_BYTES;
    if (insideOversizedLine) {
      pieces = [];
      piecesBytes = 0;
    } else {
      pieces.push(Buffer.from(rest));
      piecesBytes += rest.length;
    }
  }
  if (!insideOversizedLine && piecesBytes > 0) onLine(Buffer.concat(pieces));
}

function addToTimeline(timeline, seenEntries, line) {
  if (!line.includes(TOOL_USE_MARK) && !line.includes(COMPACTION_MARK)) return;
  let entry;
  try {
    entry = JSON.parse(line.toString('utf8'));
  } catch {
    return;
  }
  if (!entry || seenEntries.has(entry.uuid)) return;
  if (entry.uuid) seenEntries.add(entry.uuid);
  if (entry.isCompactSummary) {
    timeline.push({ name: COMPACTION });
    return;
  }
  const content = entry.message && entry.message.content;
  if (!Array.isArray(content)) return;
  for (const block of content) {
    if (block && block.type === 'tool_use') timeline.push(timelineEntryOf(block));
  }
}

function timelineEntryOf(toolUse) {
  if (toolUse.name !== 'Skill') return { name: toolUse.name };
  return { name: toolUse.name, input: { skill: toolUse.input && toolUse.input.skill } };
}

function findLastIndex(items, predicate) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

main();
