'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const WRITE_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit', 'MultiEdit']);
const STEP_SKILLS = Object.freeze({
  test: Object.freeze(['tests-first']),
  code: Object.freeze(['code-comme-poesie', 'commencer-ferme']),
});
const CODE_EXTENSIONS = new Set(['.c', '.h', '.cc', '.cpp', '.cxx', '.hh', '.hpp', '.cu', '.cuh', '.cs', '.fs', '.java',
  '.kt', '.scala', '.go', '.rs', '.swift', '.py', '.rb', '.php', '.js', '.cjs', '.mjs', '.jsx', '.ts', '.cts', '.mts',
  '.tsx', '.vue', '.svelte', '.lua', '.dart', '.sh', '.bash', '.ps1', '.psm1']);
const TEST_FOLDER = /^(tests?|__tests__|specs?)$|[.\-_]tests?$/i;
const TEST_FILE_NAME = /^test_|^(conftest|tests?)\.py$|[._-](test|spec)\.|(^|[A-Za-z0-9])Tests?\.[^.]+$/;

function stepOfWrittenFile(filePath) {
  if (typeof filePath !== 'string') return null;
  const folders = pathInsideItsRepository(filePath).split(/[\\/]/);
  const fileName = folders.pop();
  if (!CODE_EXTENSIONS.has(path.extname(fileName).toLowerCase())) return null;
  const isTestFile = TEST_FILE_NAME.test(fileName) || folders.some((folder) => TEST_FOLDER.test(folder));
  return isTestFile ? 'test' : 'code';
}

function pathInsideItsRepository(filePath) {
  const absolute = path.resolve(filePath);
  for (let folder = path.dirname(absolute); ; folder = path.dirname(folder)) {
    if (fs.existsSync(path.join(folder, '.git'))) return path.relative(folder, absolute);
    if (path.dirname(folder) === folder) return absolute;
  }
}

function missingStepSkills(filePath, loadedSkills) {
  const step = stepOfWrittenFile(filePath);
  if (step === null) return null;
  const missingSkills = STEP_SKILLS[step].filter((skill) => !loadedSkills.some((name) => isSkillNamed(name, skill)));
  return { step, missingSkills };
}

function isSkillNamed(name, skill) {
  return name === skill || name.endsWith(`:${skill}`);
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

module.exports = { WRITE_TOOLS, STEP_SKILLS, stepOfWrittenFile, missingStepSkills, isSkillNamed, isClaudeOwnOrTemporaryFile };
