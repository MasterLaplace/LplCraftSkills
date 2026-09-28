#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const WRITE_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit', 'MultiEdit']);
const COMMAND_TOOLS = new Set(['Bash', 'PowerShell']);
const AGENT_TOOLS = new Set(['Agent', 'Task']);
const SELF = 'essayeur';
const PACK_SKILLS_DIR = path.join(__dirname, '..', '..', 'skills');

const ALLOW = 0;
const NOT_CHECKED = 1;
const BLOCK = 2;

const GIT_READS = new Set([
  'status', 'log', 'show', 'diff', 'diff-tree', 'diff-index', 'diff-files', 'blame', 'annotate', 'grep',
  'ls-files', 'ls-tree', 'ls-remote', 'cat-file', 'rev-parse', 'rev-list', 'merge-base', 'merge-tree',
  'shortlog', 'describe', 'name-rev', 'for-each-ref', 'show-ref', 'show-branch', 'range-diff', 'cherry',
  'whatchanged', 'check-ignore', 'check-attr', 'verify-commit', 'verify-tag', 'var', 'count-objects',
  'fetch', 'clone', 'init', 'help', 'version',
]);
const GIT_READS_UNDER_CONDITION = {
  worktree: (args) => /^\s*(add|list)(\s|$)/.test(args),
  branch: isBranchListing,
  tag: (args) => /^\s*$|(^|\s)(-l|--list|--contains|--points-at|--merged|--no-merged)(\s|=|$)/.test(args),
  remote: (args) => /^\s*$|^\s*(-v|--verbose|show|get-url)(\s|$)/.test(args),
  config: (args) => /(^|\s)(--get|--get-all|--get-regexp|--list|-l)(\s|=|$)/.test(args)
    || /^\s*(--(global|system|local|worktree)\s+)?[\w-]+(\.[\w.-]+)+\s*$/.test(args),
  stash: (args) => /^\s*(list|show)(\s|$)/.test(args),
  reflog: (args) => !/^\s*(expire|delete)(\s|$)/.test(args),
};
const GIT_GLOBAL_OPTIONS = /^(?:\s+(?:-C|-c|--git-dir|--work-tree|--namespace)(?:\s+|=)(?:"[^"]*"|'[^']*'|\S+)|\s+(?:-P|-p|--paginate|--no-pager|--no-optional-locks|--literal-pathspecs|--no-replace-objects|--bare))*/;

const BRANCH_LISTING_FLAGS = new Set([
  '--show-current', '--list', '-l', '-a', '--all', '-r', '--remotes', '-v', '-vv', '--verbose',
  '--column', '--no-column', '--color', '--no-color', '-i', '--ignore-case',
]);
const BRANCH_FLAGS_WITH_VALUE = new Set(['--contains', '--no-contains', '--merged', '--no-merged', '--points-at', '--sort', '--format']);

const GH_READ_VERBS = new Set(['view', 'diff', 'checks', 'list', 'status', 'download', 'watch']);
const GH_READ_GROUPS = new Set(['search', 'help', 'version', 'status']);

const PUBLISHERS = [
  /\b(npm|yarn|pnpm)\s+publish\b/,
  /\b(dotnet\s+nuget|nuget)\s+push\b/,
  /\bdocker\s+push\b/,
  /\btwine\s+upload\b/,
  /\bcargo\s+publish\b/,
  /\bgem\s+push\b/,
];

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
  if (mode !== 'pre') {
    process.stderr.write(`essayeur-gate : mode inconnu '${mode}'. Attendu : pre.\n`);
    return NOT_CHECKED;
  }
  const toolInput = input.tool_input || {};
  if (WRITE_TOOLS.has(input.tool_name)) return refuse(writeRefusal());
  if (AGENT_TOOLS.has(input.tool_name)) return refuse(agentRefusal(toolInput.subagent_type));
  if (input.tool_name === 'Skill') return refuse(skillRefusal(toolInput.skill));
  if (!COMMAND_TOOLS.has(input.tool_name)) return ALLOW;
  return refuse(commandRefusal(String(toolInput.command || '')));
}

function refuse(message) {
  if (message === null) return ALLOW;
  process.stderr.write(`${message}\n`);
  return BLOCK;
}

function writeRefusal() {
  return `L'essayeur ne modifie aucun fichier : il relit, il ne corrige pas. Le rapport est ta reponse `
    + `finale ; un correctif se propose dans le rapport, en esquisse. Un script de travail s'ecrit dans `
    + `le dossier temporaire, par une commande.`;
}

function agentRefusal(subagentType) {
  if (isSelf(subagentType)) return null;
  return `Un sous-agent de l'essayeur est un essayeur : relance avec subagent_type '${SELF}'. Un autre `
    + `type (${subagentType ? `'${subagentType}'` : 'absent, donc general-purpose'}) n'aurait pas ses rails.`;
}

function isSelf(name) {
  return typeof name === 'string' && (name === SELF || name.endsWith(`:${SELF}`));
}

function skillRefusal(skill) {
  const name = typeof skill === 'string' ? skill.split(':').pop() : '';
  if (name && fs.existsSync(path.join(PACK_SKILLS_DIR, name, 'SKILL.md'))) return null;
  return `L'essayeur ne charge que les skills du pack (${PACK_SKILLS_DIR}) : '${skill}' n'en est pas, et `
    + `un skill d'ailleurs peut publier ou ecrire par un chemin que ce rail ne voit pas.`;
}

function commandRefusal(command) {
  const refused = segments(command).map(refusalOf).find((reason) => reason !== null);
  if (!refused) return null;
  return `Refuse par le rail de l'essayeur : ${refused}. Une revue reste locale jusqu'a ce qu'un humain `
    + `decide de la publier, et elle ne change l'etat d'aucun depot. Si tu cherchais seulement du texte, `
    + `passe par l'outil Grep plutot que par une commande qui le contient.`;
}

function segments(command) {
  return command.split(/&&|\|\||;|\||\n/).map((part) => part.trim()).filter(Boolean);
}

function refusalOf(segment) {
  return gitRefusal(segment) ?? ghRefusal(segment) ?? networkRefusal(segment) ?? publisherRefusal(segment);
}

function gitRefusal(segment) {
  const start = segment.search(/(^|\s)git(\s|$)/);
  if (start < 0) return null;
  const afterGit = segment.slice(segment.indexOf('git', start) + 3);
  const rest = afterGit.slice(afterGit.match(GIT_GLOBAL_OPTIONS)[0].length);
  const match = rest.match(/^\s+([a-z][a-z-]*)(.*)$/);
  if (!match) {
    return /^\s*(--version|--help)?\s*$/.test(rest) ? null : `'git${rest}' a une forme que le rail ne reconnait pas`;
  }
  const [, subcommand, args] = match;
  if (GIT_READS.has(subcommand)) return null;
  const condition = GIT_READS_UNDER_CONDITION[subcommand];
  if (condition && condition(args)) return null;
  return `'git ${subcommand}${args.trim() ? ` ${args.trim().split(/\s+/)[0]}` : ''}' change l'etat d'un depot`;
}

function isBranchListing(args) {
  const tokens = args.trim().split(/\s+/).filter(Boolean);
  const listing = tokens.includes('--list') || tokens.includes('-l');
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const flag = token.split('=')[0];
    if (BRANCH_FLAGS_WITH_VALUE.has(flag)) {
      if (!token.includes('=')) index += 1;
      continue;
    }
    if (BRANCH_LISTING_FLAGS.has(token)) continue;
    if (listing && !token.startsWith('-')) continue;
    return false;
  }
  return true;
}

function ghRefusal(segment) {
  const match = segment.match(/(^|\s)gh\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?(.*)$/);
  if (!match) return null;
  const [, , group, verb, rest] = match;
  if (group === 'api') return ghApiRefusal(`${verb ?? ''} ${rest}`);
  if (GH_READ_GROUPS.has(group)) return null;
  if (group === 'auth' && verb === 'status') return null;
  if (group === 'repo' && verb === 'clone') return null;
  if (verb && GH_READ_VERBS.has(verb)) return null;
  return `'gh ${group}${verb ? ` ${verb}` : ''}' n'est pas une lecture connue de la forge`;
}

function ghApiRefusal(args) {
  const method = (args.match(/(?:-X\s*|--method(?:\s+|=))([A-Za-z]+)/) || [])[1];
  if (method) {
    return method.toUpperCase() === 'GET' ? null : `'gh api' en ${method.toUpperCase()} ecrit sur la forge`;
  }
  if (/(^|\s)graphql(\s|$)/.test(args)) {
    return /\bmutation\b/.test(args) ? `'gh api graphql' avec une mutation ecrit sur la forge` : null;
  }
  return /(^|\s)(-f|-F|--field|--raw-field|--input)(\s|=)/.test(args)
    ? `'gh api' avec des champs passe en POST, donc ecrit sur la forge`
    : null;
}

function networkRefusal(segment) {
  if (/(^|\s)curl(\s|$)/.test(segment)
      && (/(-X|--request)\s*(POST|PUT|PATCH|DELETE)\b/i.test(segment)
        || /(^|\s)(-d|--data|--data-raw|--data-binary|--data-urlencode|--json|-F|--form|-T|--upload-file)(\s|=|@|$)/.test(segment))) {
    return `'curl' envoie des donnees`;
  }
  if (/(^|\s)wget(\s|$)/.test(segment) && /--(method=(POST|PUT|PATCH|DELETE)|post-data|post-file|body-data|body-file)/i.test(segment)) {
    return `'wget' envoie des donnees`;
  }
  if (/(^|\s|\()(Invoke-RestMethod|Invoke-WebRequest|irm|iwr)(\s|$)/i.test(segment)
      && /-Method\s+(Post|Put|Patch|Delete)\b|(^|\s)-Body(\s|$)/i.test(segment)) {
    return `'Invoke-RestMethod' ou 'Invoke-WebRequest' envoie des donnees`;
  }
  return null;
}

function publisherRefusal(segment) {
  const publisher = PUBLISHERS.find((pattern) => pattern.test(segment));
  return publisher ? `'${segment.match(publisher)[0]}' publie un artefact` : null;
}

main();
