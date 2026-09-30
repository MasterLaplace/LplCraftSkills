'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const GATE = path.join(__dirname, 'essayeur-gate.cjs');

function run(mode, input) {
  const done = spawnSync(process.execPath, [GATE, mode], { input: JSON.stringify(input), encoding: 'utf8' });
  return { code: done.status, stderr: done.stderr };
}
const shell = (command, tool = 'Bash') => run('pre', { tool_name: tool, tool_input: { command } });

function assertAllowed(command, tool) {
  const { code, stderr } = shell(command, tool);
  assert.equal(code, 0, `${command}\n${stderr}`);
}
function assertBlocked(command, tool) {
  const { code, stderr } = shell(command, tool);
  assert.equal(code, 2, command);
  return stderr;
}


test('writing a file is refused, and the message says where the report goes', () => {
  for (const tool of ['Write', 'Edit', 'NotebookEdit', 'MultiEdit']) {
    const { code, stderr } = run('pre', { tool_name: tool, tool_input: { file_path: 'a.ts' } });
    assert.equal(code, 2, tool);
    assert.match(stderr, /report/);
  }
});

test('reading, searching and exploring pass', () => {
  for (const tool of ['Read', 'Grep', 'Glob', 'WebFetch']) {
    assert.equal(run('pre', { tool_name: tool, tool_input: {} }).code, 0, tool);
  }
});

test('reads of the forge pass', () => {
  assertAllowed('gh pr view 12 --json body,files');
  assertAllowed('gh pr diff 12');
  assertAllowed('gh pr checks 12');
  assertAllowed('gh run view --job 1 --log');
  assertAllowed('gh repo clone o/r /tmp/review-r');
  assertAllowed('gh repo view --json visibility');
  assertAllowed('gh search prs --author x');
  assertAllowed('gh auth status');
});

test('commenting, reviewing, approving or merging on the forge is refused, and the message names the command', () => {
  const stderr = assertBlocked('gh pr comment 12 --body "see line 4"');
  assert.match(stderr, /gh pr comment/);
  assertBlocked('gh pr review 12 --approve');
  assertBlocked('gh pr review 12 --request-changes -b x');
  assertBlocked('gh pr merge 12 --squash');
  assertBlocked('gh pr close 12');
  assertBlocked('gh pr edit 12 --add-label x');
  assertBlocked('gh issue comment 4 -b x');
  assertBlocked('gh run rerun 99');
});

test('a forge verb that is not a known read is refused: start closed', () => {
  assertBlocked('gh pr checkout 12');
  assertBlocked('gh repo fork');
  assertBlocked('gh workflow run ci.yml');
});

test('gh api for reading passes', () => {
  assertAllowed('gh api repos/o/r/pulls/12');
  assertAllowed('gh api -X GET repos/o/r/pulls/12/comments');
  assertAllowed("gh api graphql -f query='query { viewer { login } }'");
});

test('gh api that writes is refused, including when the method is implicit', () => {
  assertBlocked('gh api -X POST repos/o/r/issues/12/comments -f body=x');
  assertBlocked('gh api --method=PATCH repos/o/r/pulls/12 -f title=x');
  assertBlocked('gh api repos/o/r/issues/12/comments -f body=x');
  assertBlocked('gh api repos/o/r/pulls/12/reviews --input review.json');
  assertBlocked('gh api -XPUT repos/o/r/pulls/12/merge');
  assertBlocked('gh api -XDELETE repos/o/r/git/refs/heads/x');
  assertBlocked("gh api graphql -f query='mutation { addComment(input: {}) { clientMutationId } }'");
});

test('git reads and the worktree pass', () => {
  assertAllowed('git -C "C:/Code/Repo/a repository" log --oneline -5');
  assertAllowed('git fetch origin pull/12/head');
  assertAllowed('git worktree add --detach /tmp/review-12 FETCH_HEAD');
  assertAllowed('git worktree list');
  assertAllowed('git diff abc1234..def5678 -- src/');
  assertAllowed('git -P log -1');
  assertAllowed('git diff-tree --no-commit-id --name-only -r HEAD');
  assertAllowed('git merge-tree --write-tree main HEAD');
  assertAllowed('git verify-commit HEAD');
  assertAllowed('git reflog -10');
  assertAllowed('git config user.name');
  assertAllowed('git clone https://example.org/o/r.git /tmp/r');
  assertAllowed('git -C /tmp/repro init');
  assertAllowed('git show HEAD:README.md');
  assertAllowed('git branch --show-current');
  assertAllowed('git stash list');
  assertAllowed('git config --get user.name');
});

test('what changes the state of a repository is refused', () => {
  assertBlocked('git push origin HEAD');
  assertBlocked('git -C ../x push --force-with-lease');
  assertBlocked('git checkout main');
  assertBlocked('git switch feat/x');
  assertBlocked('git stash');
  assertBlocked('git reset --hard HEAD~1');
  assertBlocked('git commit -m "fix"');
  assertBlocked('git branch -D review-12');
  assertBlocked('git branch review-12 FETCH_HEAD');
  assertBlocked('git branch --unset-upstream');
  assertBlocked('git config user.name x');
  assertBlocked('git reflog expire --all');
  assertBlocked('git worktree remove --force ../other');
  assertBlocked('git worktree prune');
});

test('a shell redirection does not turn a read into a write, nor the reverse', () => {
  assertAllowed('git branch -a --contains abc1234 2>/dev/null');
  assertAllowed('git -C ../r branch -r --contains abc1234 2>&1');
  assertAllowed('git branch --list "review-*" > branches.txt');
  assertAllowed('git remote 2>/dev/null');
  assertAllowed('git tag 2> errors.txt');
  assertBlocked('git branch review-12 2>/dev/null');
  assertBlocked('git branch -D review-12 2>&1');
  assertBlocked('git remote add upstream https://example.org/o/r.git 2>/dev/null');
});

test('a git form the rail does not recognise is refused by default', () => {
  assertBlocked('git -P push origin HEAD');
  assertBlocked('git -p commit -am x');
  assertBlocked('git --paginate push');
  assertBlocked('git --no-optional-locks checkout main');
});

test('a refused command in the middle of a chain blocks the chain', () => {
  assertBlocked('cd repo && gh pr view 12 && gh pr comment 12 -b x');
  assertBlocked('git log -1; git push');
  assertBlocked('git status | tee x && git commit -am x');
});

test('sending data over the network is refused, reading passes', () => {
  assertAllowed('curl -s https://api.github.com/repos/o/r');
  assertAllowed('curl -s -f https://api.github.com/repos/o/r');
  assertAllowed('curl -sS -D - https://example.org/x.json');
  assertBlocked('curl -X POST https://api.github.com/repos/o/r/issues/1/comments -d @body.json');
  assertBlocked('curl --data "x=1" https://example.org');
  assertBlocked('Invoke-RestMethod -Method Post -Uri https://example.org -Body $b', 'PowerShell');
  assertBlocked('irm -Method Post -Uri https://example.org -Body $b', 'PowerShell');
  assertBlocked('iwr -Method Delete -Uri https://example.org/x', 'PowerShell');
});

test('publishing a package or an image is refused, building passes', () => {
  assertAllowed('npm ci --ignore-scripts');
  assertAllowed('dotnet test tests/X.Tests');
  assertBlocked('npm publish');
  assertBlocked('docker push registry/x:1');
  assertBlocked('dotnet nuget push x.nupkg');
});

test('a subagent of the essayeur is an essayeur: any other type is refused, the missing one included', () => {
  const launch = (input) => run('pre', { tool_name: 'Agent', tool_input: input }).code;
  assert.equal(launch({ prompt: 'x', subagent_type: 'essayeur' }), 0);
  assert.equal(launch({ prompt: 'x', subagent_type: 'craft:essayeur' }), 0);
  assert.equal(launch({ prompt: 'x' }), 2);
  assert.equal(launch({ prompt: 'x', subagent_type: 'general-purpose' }), 2);
  assert.equal(launch({ prompt: 'x', subagent_type: 'Explore' }), 2);
  assert.equal(run('pre', { tool_name: 'Task', tool_input: { prompt: 'x' } }).code, 2);
});

test('only the pack skills load: a skill from elsewhere can publish', () => {
  const load = (skill) => run('pre', { tool_name: 'Skill', tool_input: { skill } }).code;
  assert.equal(load('relire-une-pr'), 0);
  assert.equal(load('craft:garder-les-frontieres'), 0);
  assert.equal(load('code-review'), 2);
  assert.equal(load(undefined), 2);
});

test('PowerShell is guarded like Bash', () => {
  assertAllowed('git log --oneline -3', 'PowerShell');
  assertBlocked('gh pr comment 12 -b x', 'PowerShell');
});

test('an unknown mode is a calling error, not a silent pass', () => {
  const { code, stderr } = run('elsewhere', { tool_name: 'Bash', tool_input: { command: 'gh pr comment 1' } });
  assert.equal(code, 1);
  assert.match(stderr, /pre/);
});
