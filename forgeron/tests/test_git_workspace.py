"""The git adapter, against a real repository. No GitHub, no network.

A bare repository on disk plays origin, which is enough to exercise everything the
driver relies on: a worktree per issue, a branch renamed before its first push, and
`is_synced` telling the truth about what actually left the machine. That last one is
the check that catches an agent overstating its verdict, so it is the one that must
not be tested with a fake.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from forgeron.git_workspace import GitWorkspace


def git(cwd: str, *argv: str) -> str:
    done = subprocess.run(["git", "-C", cwd, *argv], capture_output=True, text=True, check=True)
    return done.stdout.strip()


class RealGit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tempfile.mkdtemp()
        cls.origin = os.path.join(cls.root, "origin.git")
        cls.clone = os.path.join(cls.root, "clone")

        subprocess.run(["git", "init", "--bare", "-b", "main", cls.origin],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", cls.origin, cls.clone], capture_output=True, check=True)
        git(cls.clone, "config", "user.email", "forgeron@example.invalid")
        git(cls.clone, "config", "user.name", "forgeron")
        with open(os.path.join(cls.clone, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("base\n")
        git(cls.clone, "add", "-A")
        git(cls.clone, "commit", "-m", "chore: base")
        git(cls.clone, "push", "-u", "origin", "main")

    def setUp(self) -> None:
        self.workspace = GitWorkspace()
        self.worktree = os.path.join(self.root, "wt", self.id().rsplit(".", 1)[1])

    def tearDown(self) -> None:
        self.workspace.discard(self.worktree, self.clone)

    def test_a_worktree_is_created_on_a_new_branch_from_base(self) -> None:
        self.workspace.prepare(self.clone, self.worktree, "forgeron/issue-1", "main")
        self.assertTrue(os.path.isfile(os.path.join(self.worktree, "README.md")))
        self.assertEqual(git(self.worktree, "rev-parse", "--abbrev-ref", "HEAD"),
                         "forgeron/issue-1")
        self.assertFalse(self.workspace.has_commits_ahead(self.worktree, "main"))

    def test_the_human_checkout_is_left_alone(self) -> None:
        before = git(self.clone, "rev-parse", "--abbrev-ref", "HEAD")
        self.workspace.prepare(self.clone, self.worktree, "forgeron/issue-2", "main")
        with open(os.path.join(self.worktree, "new.txt"), "w", encoding="utf-8") as handle:
            handle.write("written by the agent\n")
        self.assertEqual(git(self.clone, "rev-parse", "--abbrev-ref", "HEAD"), before)
        self.assertEqual(git(self.clone, "status", "--porcelain"), "",
                         "le checkout de l'humain doit rester propre")
        self.assertFalse(os.path.exists(os.path.join(self.clone, "new.txt")))

    def test_preparing_twice_reuses_the_worktree(self) -> None:
        self.workspace.prepare(self.clone, self.worktree, "forgeron/issue-3", "main")
        self.workspace.commit_empty(self.worktree, "chore: amorce")
        head = self.workspace.head(self.worktree)
        self.workspace.prepare(self.clone, self.worktree, "forgeron/issue-3", "main")
        self.assertEqual(self.workspace.head(self.worktree), head,
                         "re-entrer apres un crash ne doit pas jeter le travail")

    def test_rename_then_push_then_sync_reports_the_truth(self) -> None:
        self.workspace.prepare(self.clone, self.worktree, "forgeron/issue-4", "main")
        self.workspace.rename_branch(self.worktree, "feat/cache-lru")
        self.workspace.commit_empty(self.worktree, "chore(cache-lru): amorce pour #4")
        self.assertTrue(self.workspace.has_commits_ahead(self.worktree, "main"))

        # Not pushed yet: the claim "pushed" would be a lie, and this is what catches it.
        self.assertFalse(self.workspace.is_synced(self.worktree, "feat/cache-lru"))
        self.workspace.push(self.worktree, "feat/cache-lru")
        self.assertTrue(self.workspace.is_synced(self.worktree, "feat/cache-lru"))

        # A commit made after the push must make it unsynced again, otherwise the
        # check would only ever notice a branch that never left at all.
        with open(os.path.join(self.worktree, "cache.py"), "w", encoding="utf-8") as handle:
            handle.write("cache = {}\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-m", "feat(cache): un cache")
        self.assertFalse(self.workspace.is_synced(self.worktree, "feat/cache-lru"))

    def test_an_already_pushed_branch_is_tracked_rather_than_restarted(self) -> None:
        first = os.path.join(self.root, "wt", "resume-a")
        self.workspace.prepare(self.clone, first, "feat/resume-me", "main")
        self.workspace.commit_empty(first, "chore: travail deja pousse")
        self.workspace.push(first, "feat/resume-me")
        pushed_head = self.workspace.head(first)
        self.workspace.discard(first, self.clone)

        # Another machine, or the same one after a crash: the branch exists remotely
        # and restarting from base would silently drop reviewed work.
        self.workspace.prepare(self.clone, self.worktree, "feat/resume-me", "main")
        self.assertEqual(self.workspace.head(self.worktree), pushed_head)

    def test_discard_removes_the_worktree_and_keeps_the_branch(self) -> None:
        self.workspace.prepare(self.clone, self.worktree, "feat/keep-me", "main")
        self.workspace.commit_empty(self.worktree, "chore: amorce")
        self.workspace.push(self.worktree, "feat/keep-me")
        self.workspace.discard(self.worktree, self.clone)
        self.assertFalse(os.path.isdir(self.worktree))
        self.assertIn("feat/keep-me", git(self.clone, "ls-remote", "--heads", "origin"),
                      "la branche est le seul instantane qui survit a la machine")


class RealConflict(RealGit):
    """Un vrai conflit, avec de vrais marqueurs, contre un vrai depot.

    C'est le chemin dont tout le reste depend et le seul que des fakes ne peuvent
    pas prouver : `sync_with_base` doit laisser l'operation EN COURS pour que
    l'agent voie les marqueurs, et `conflicted` doit dire non tant qu'elle ne l'est
    pas. Une resolution crue sur parole est exactement ce qui pousse une branche a
    moitie rebasee.
    """

    def _branch_that_fights_with_base(self, name: str) -> None:
        """Fabrique le cas : la base et la branche changent la MEME ligne."""
        # Le contenu est unique par test : la classe partage un depot, et deux
        # tests qui ecrivent la meme chose sur main donnent "rien a commiter" au
        # second - un echec qui ressemble a un bug de git et n'en est pas un.
        marque = name.replace("/", "-")
        self.workspace.prepare(self.clone, self.worktree, name, "main")
        self._write(self.worktree, "partage.txt", f"la version de la branche {marque}\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-m", f"feat: version de la branche {marque}")

        # pendant ce temps, quelqu'un d'autre pousse sur main
        git(self.clone, "checkout", "main", "--quiet")
        git(self.clone, "pull", "--quiet", "origin", "main")
        self._write(self.clone, "partage.txt", f"la version de main {marque}\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-m", f"feat: version de main {marque}")
        git(self.clone, "push", "origin", "main")

    @staticmethod
    def _write(directory: str, name: str, content: str) -> None:
        with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
            handle.write(content)

    def test_a_rebase_that_conflicts_reports_the_files_and_stays_in_progress(self) -> None:
        self._branch_that_fights_with_base("feat/1-conflit")
        clean, conflicted = self.workspace.sync_with_base(self.worktree, "main", "REBASE")

        self.assertFalse(clean)
        self.assertEqual(conflicted, ["partage.txt"])
        self.assertEqual(self.workspace.conflicted(self.worktree), ["partage.txt"],
                         "la question doit pouvoir etre reposee, c'est elle qui verifie l'agent")
        with open(os.path.join(self.worktree, "partage.txt"), encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("<<<<<<<", body, "les marqueurs sont la matiere de la resolution")
        self.assertIn("la version de main", body)
        self.assertIn("la version de la branche", body)
        self.workspace.abort_sync(self.worktree)

    def test_resolving_then_continuing_clears_it_and_the_push_overwrites(self) -> None:
        self._branch_that_fights_with_base("feat/2-resolu")
        self.workspace.sync_with_base(self.worktree, "main", "REBASE")

        self._write(self.worktree, "partage.txt", "les deux versions, tenues ensemble\n")
        git(self.worktree, "add", "partage.txt")
        subprocess.run(["git", "-C", self.worktree, "-c", "core.editor=true",
                        "rebase", "--continue"], capture_output=True, check=True)

        self.assertEqual(self.workspace.conflicted(self.worktree), [])
        self.workspace.push(self.worktree, "feat/2-resolu")
        self.assertTrue(self.workspace.is_synced(self.worktree, "feat/2-resolu"))

    def test_a_rebased_branch_needs_the_forced_push_and_a_plain_one_is_refused(self) -> None:
        self._branch_that_fights_with_base("feat/3-force")
        self.workspace.push(self.worktree, "feat/3-force")     # publiee telle quelle
        self.workspace.sync_with_base(self.worktree, "main", "REBASE")
        self._write(self.worktree, "partage.txt", "les deux, ensemble\n")
        git(self.worktree, "add", "partage.txt")
        subprocess.run(["git", "-C", self.worktree, "-c", "core.editor=true",
                        "rebase", "--continue"], capture_output=True, check=True)

        # L'historique a ete reecrit : un push ordinaire DOIT etre refuse, sinon le
        # push force n'aurait aucune raison d'exister et personne ne le verifierait.
        from forgeron.git_workspace import GitError
        with self.assertRaises(GitError):
            self.workspace.push(self.worktree, "feat/3-force")
        self.workspace.push_forced(self.worktree, "feat/3-force")
        self.assertTrue(self.workspace.is_synced(self.worktree, "feat/3-force"))

    def test_abort_puts_the_branch_back_exactly_as_it_was(self) -> None:
        self._branch_that_fights_with_base("feat/4-annule")
        before = self.workspace.head(self.worktree)
        self.workspace.sync_with_base(self.worktree, "main", "REBASE")
        self.workspace.abort_sync(self.worktree)

        self.assertEqual(self.workspace.head(self.worktree), before)
        self.assertEqual(self.workspace.conflicted(self.worktree), [])

    def test_a_merge_conflicts_on_the_same_case_without_rewriting_history(self) -> None:
        self._branch_that_fights_with_base("feat/5-fusion")
        before = self.workspace.head(self.worktree)
        clean, conflicted = self.workspace.sync_with_base(self.worktree, "main", "MERGE")

        self.assertFalse(clean)
        self.assertEqual(conflicted, ["partage.txt"])
        self.workspace.abort_sync(self.worktree)
        self.assertEqual(self.workspace.head(self.worktree), before,
                         "une fusion annulee ne deplace pas la branche non plus")


if __name__ == "__main__":
    unittest.main()
