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


test('ecrire un fichier est refuse, et le message dit ou va le rapport', () => {
  for (const tool of ['Write', 'Edit', 'NotebookEdit', 'MultiEdit']) {
    const { code, stderr } = run('pre', { tool_name: tool, tool_input: { file_path: 'a.ts' } });
    assert.equal(code, 2, tool);
    assert.match(stderr, /rapport/);
  }
});

test('lire, chercher et explorer passent', () => {
  for (const tool of ['Read', 'Grep', 'Glob', 'WebFetch']) {
    assert.equal(run('pre', { tool_name: tool, tool_input: {} }).code, 0, tool);
  }
});

test('les lectures de la forge passent', () => {
  assertAllowed('gh pr view 12 --json body,files');
  assertAllowed('gh pr diff 12');
  assertAllowed('gh pr checks 12');
  assertAllowed('gh run view --job 1 --log');
  assertAllowed('gh repo clone o/r /tmp/relecture-r');
  assertAllowed('gh repo view --json visibility');
  assertAllowed('gh search prs --author x');
  assertAllowed('gh auth status');
});

test('commenter, relire, approuver ou fusionner sur la forge est refuse, et le message nomme la commande', () => {
  const stderr = assertBlocked('gh pr comment 12 --body "voir ligne 4"');
  assert.match(stderr, /gh pr comment/);
  assertBlocked('gh pr review 12 --approve');
  assertBlocked('gh pr review 12 --request-changes -b x');
  assertBlocked('gh pr merge 12 --squash');
  assertBlocked('gh pr close 12');
  assertBlocked('gh pr edit 12 --add-label x');
  assertBlocked('gh issue comment 4 -b x');
  assertBlocked('gh run rerun 99');
});

test('un verbe de la forge qui n est pas une lecture connue est refuse : on commence ferme', () => {
  assertBlocked('gh pr checkout 12');
  assertBlocked('gh repo fork');
  assertBlocked('gh workflow run ci.yml');
});

test('gh api en lecture passe', () => {
  assertAllowed('gh api repos/o/r/pulls/12');
  assertAllowed('gh api -X GET repos/o/r/pulls/12/comments');
  assertAllowed("gh api graphql -f query='query { viewer { login } }'");
});

test('gh api qui ecrit est refuse, y compris quand la methode est implicite', () => {
  assertBlocked('gh api -X POST repos/o/r/issues/12/comments -f body=x');
  assertBlocked('gh api --method=PATCH repos/o/r/pulls/12 -f title=x');
  assertBlocked('gh api repos/o/r/issues/12/comments -f body=x');
  assertBlocked('gh api repos/o/r/pulls/12/reviews --input review.json');
  assertBlocked('gh api -XPUT repos/o/r/pulls/12/merge');
  assertBlocked('gh api -XDELETE repos/o/r/git/refs/heads/x');
  assertBlocked("gh api graphql -f query='mutation { addComment(input: {}) { clientMutationId } }'");
});

test('les lectures git et le worktree passent', () => {
  assertAllowed('git -C "C:/Code/Repo/un depot" log --oneline -5');
  assertAllowed('git fetch origin pull/12/head');
  assertAllowed('git worktree add --detach /tmp/relecture-12 FETCH_HEAD');
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

test('ce qui change l etat d un depot est refuse', () => {
  assertBlocked('git push origin HEAD');
  assertBlocked('git -C ../x push --force-with-lease');
  assertBlocked('git checkout main');
  assertBlocked('git switch feat/x');
  assertBlocked('git stash');
  assertBlocked('git reset --hard HEAD~1');
  assertBlocked('git commit -m "fix"');
  assertBlocked('git branch -D relecture-12');
  assertBlocked('git branch relecture-12 FETCH_HEAD');
  assertBlocked('git branch --unset-upstream');
  assertBlocked('git config user.name x');
  assertBlocked('git reflog expire --all');
  assertBlocked('git worktree remove --force ../autre');
  assertBlocked('git worktree prune');
});

test('une redirection du shell ne transforme pas une lecture en ecriture, ni l inverse', () => {
  assertAllowed('git branch -a --contains abc1234 2>/dev/null');
  assertAllowed('git -C ../r branch -r --contains abc1234 2>&1');
  assertAllowed('git branch --list "relecture-*" > branches.txt');
  assertAllowed('git remote 2>/dev/null');
  assertAllowed('git tag 2> erreurs.txt');
  assertBlocked('git branch relecture-12 2>/dev/null');
  assertBlocked('git branch -D relecture-12 2>&1');
  assertBlocked('git remote add amont https://example.org/o/r.git 2>/dev/null');
});

test('une forme de git que le rail ne reconnait pas est refusee par defaut', () => {
  assertBlocked('git -P push origin HEAD');
  assertBlocked('git -p commit -am x');
  assertBlocked('git --paginate push');
  assertBlocked('git --no-optional-locks checkout main');
});

test('une commande refusee au milieu d une chaine bloque la chaine', () => {
  assertBlocked('cd repo && gh pr view 12 && gh pr comment 12 -b x');
  assertBlocked('git log -1; git push');
  assertBlocked('git status | tee x && git commit -am x');
});

test('envoyer des donnees par le reseau est refuse, lire passe', () => {
  assertAllowed('curl -s https://api.github.com/repos/o/r');
  assertAllowed('curl -s -f https://api.github.com/repos/o/r');
  assertAllowed('curl -sS -D - https://example.org/x.json');
  assertBlocked('curl -X POST https://api.github.com/repos/o/r/issues/1/comments -d @body.json');
  assertBlocked('curl --data "x=1" https://example.org');
  assertBlocked('Invoke-RestMethod -Method Post -Uri https://example.org -Body $b', 'PowerShell');
  assertBlocked('irm -Method Post -Uri https://example.org -Body $b', 'PowerShell');
  assertBlocked('iwr -Method Delete -Uri https://example.org/x', 'PowerShell');
});

test('publier un paquet ou une image est refuse, construire passe', () => {
  assertAllowed('npm ci --ignore-scripts');
  assertAllowed('dotnet test tests/X.Tests');
  assertBlocked('npm publish');
  assertBlocked('docker push registry/x:1');
  assertBlocked('dotnet nuget push x.nupkg');
});

test('un sous-agent de l essayeur est un essayeur : tout autre type est refuse, y compris l absent', () => {
  const launch = (input) => run('pre', { tool_name: 'Agent', tool_input: input }).code;
  assert.equal(launch({ prompt: 'x', subagent_type: 'essayeur' }), 0);
  assert.equal(launch({ prompt: 'x', subagent_type: 'craft:essayeur' }), 0);
  assert.equal(launch({ prompt: 'x' }), 2);
  assert.equal(launch({ prompt: 'x', subagent_type: 'general-purpose' }), 2);
  assert.equal(launch({ prompt: 'x', subagent_type: 'Explore' }), 2);
  assert.equal(run('pre', { tool_name: 'Task', tool_input: { prompt: 'x' } }).code, 2);
});

test('seuls les skills du pack se chargent : un skill d ailleurs peut publier', () => {
  const load = (skill) => run('pre', { tool_name: 'Skill', tool_input: { skill } }).code;
  assert.equal(load('relire-une-pr'), 0);
  assert.equal(load('craft:garder-les-frontieres'), 0);
  assert.equal(load('code-review'), 2);
  assert.equal(load(undefined), 2);
});

test('PowerShell est garde comme Bash', () => {
  assertAllowed('git log --oneline -3', 'PowerShell');
  assertBlocked('gh pr comment 12 -b x', 'PowerShell');
});

test('un mode inconnu est une erreur d appel, pas un laisser-passer silencieux', () => {
  const { code, stderr } = run('ailleurs', { tool_name: 'Bash', tool_input: { command: 'gh pr comment 1' } });
  assert.equal(code, 1);
  assert.match(stderr, /pre/);
});
