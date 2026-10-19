'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { STEP_SKILLS, stepOfWrittenFile, missingStepSkills } = require('./write-rules.cjs');

const outsideAnyRepository = (...parts) => path.join(path.parse(process.cwd()).root, 'no-repository-here', ...parts);

test('the step of a written file is read from its folders, its name and its extension, one rule at a time', () => {
  const expected = {
    'tests/helpers.py': 'test',
    'src/Billing.Tests/Fixture.cs': 'test',
    'web/billing-tests/fixture.ts': 'test',
    'spec/support/factory.rb': 'test',
    'web/src/app/__tests__/billing.tsx': 'test',
    'src/ProrationTest.cs': 'test',
    'src/HTTPTests.cs': 'test',
    'test_engine.py': 'test',
    'tests.py': 'test',
    'conftest.py': 'test',
    'pkg/proration_test.go': 'test',
    'lib/proration_spec.rb': 'test',
    'web/src/app/billing.spec.ts': 'test',
    'web/e2e/app.e2e-spec.ts': 'test',
    'agents/hooks/artisan-gate.test.cjs': 'test',
    'src/QA.Infra/Repositories/E2eRunsRepository.cs': 'code',
    'src/Program.CS': 'code',
    'src/latest.js': 'code',
    'src/Contest.cs': 'code',
    'src/attest.go': 'code',
    'scripts/deploy.sh': 'code',
    'kernels/scan.cu': 'code',
    'docs/README.md': null,
    'tests/fixtures/run.json': null,
    'notebooks/probe.ipynb': null,
  };
  for (const [relativePath, step] of Object.entries(expected)) {
    assert.equal(stepOfWrittenFile(outsideAnyRepository(...relativePath.split('/'))), step, relativePath);
  }
  assert.equal(stepOfWrittenFile(undefined), null);
});

test('the folders above the repository do not make a file a test', () => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'write-rules-'));
  const repository = path.join(sandbox, 'billing-tests');
  fs.mkdirSync(path.join(repository, '.git'), { recursive: true });
  assert.equal(stepOfWrittenFile(path.join(repository, 'src', 'Invoice.cs')), 'code');
  assert.equal(stepOfWrittenFile(path.join(repository, 'tests', 'InvoiceFixture.cs')), 'test');
  const worktree = path.join(sandbox, 'billing-tests-worktree');
  fs.mkdirSync(path.join(worktree, 'src'), { recursive: true });
  fs.writeFileSync(path.join(worktree, '.git'), 'gitdir: elsewhere\n');
  assert.equal(stepOfWrittenFile(path.join(worktree, 'src', 'Invoice.cs')), 'code');
});

test('a reader of past sessions gets the same verdict as the rail for one write', () => {
  assert.deepEqual(missingStepSkills(outsideAnyRepository('src', 'Billing.cs'), ['cycle-de-dev', 'code-comme-poesie']),
                   { step: 'code', missingSkills: ['commencer-ferme'] });
  assert.deepEqual(missingStepSkills(outsideAnyRepository('tests', 'test_billing.py'), ['craft:tests-first']),
                   { step: 'test', missingSkills: [] });
  assert.equal(missingStepSkills(outsideAnyRepository('README.md'), []), null);
});

test('the rail asks for the skills that the step table of cycle-de-dev names for the test and code steps', () => {
  const map = fs.readFileSync(path.join(__dirname, '..', '..', 'skills', 'cycle-de-dev', 'SKILL.md'), 'utf8');
  const section = map.split(/^## /m).find((part) => part.startsWith('Ce que chaque étape charge'));
  assert.ok(section, "the section 'Ce que chaque étape charge' of cycle-de-dev was not found");
  const rows = new Map();
  for (const line of section.split('\n')) {
    const cells = line.split('|').map((cell) => cell.trim());
    if (cells.length < 4) continue;
    const skills = [...cells[2].matchAll(/`([a-z0-9-]+)`/g)].map((match) => match[1]);
    if (skills.length === 0) continue;
    assert.ok(!rows.has(cells[1]), `the step '${cells[1]}' appears twice in the table`);
    rows.set(cells[1], skills);
  }
  assert.ok(rows.size >= 8, `the step table of cycle-de-dev has ${rows.size} rows`);
  assert.deepEqual(Object.keys(STEP_SKILLS).sort(), ['code', 'test']);
  for (const [step, skills] of Object.entries(STEP_SKILLS)) {
    assert.deepEqual(skills, rows.get(step), step);
  }
});
