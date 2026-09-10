"""Le Dockerfile et les manifestes, verifies contre le code qu'ils deploient.

Ni docker ni kubectl ne sont installes ici, donc rien ne peut etre construit ni
applique. Mais deux classes d'erreurs sont verifiables hors ligne, et ce sont
justement celles qui coutent le plus cher a decouvrir dans un pod :

- une configuration que `config.load()` refuserait. Un JSON casse dans un ConfigMap
  ne se voit qu'au demarrage du conteneur, apres le build et le push ;
- un chemin ou un nom d'image qui ne concorde plus entre le Dockerfile, le compose
  et le Job. C'est de la duplication : trois fichiers nomment la meme image.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import unittest

from forgeron.config import Config, RepoConfig
from forgeron.states import Limits

ROOT = pathlib.Path(__file__).resolve().parents[1]


def configmap_json() -> dict:
    raw = (ROOT / "k8s" / "20-configmap.yaml").read_text(encoding="utf-8")
    body = raw.split("config.json: |", 1)[1]
    dedented = "\n".join(line[4:] if line.startswith("    ") else line
                         for line in body.splitlines())
    return json.loads(dedented)


class ConfigMap(unittest.TestCase):
    def test_the_embedded_configuration_is_one_the_loader_accepts(self) -> None:
        raw = configmap_json()
        for holder, payload in ((Config, raw),
                                (Limits, raw.get("limits", {}))):
            known = {field.name for field in dataclasses.fields(holder)}
            with self.subTest(holder=holder.__name__):
                self.assertEqual(set(payload) - known - {"repos"}, set())
        known_repo = {field.name for field in dataclasses.fields(RepoConfig)}
        for repo in raw["repos"]:
            self.assertEqual(set(repo) - known_repo, set())

    def test_paths_are_the_ones_the_job_mounts(self) -> None:
        raw = configmap_json()
        job = (ROOT / "k8s" / "30-job.yaml").read_text(encoding="utf-8")
        # `home` is where the state lives and `path` is where a clone is expected;
        # both are paths INSIDE the pod, and a config copied from a laptop names
        # neither. This is the check that catches that.
        self.assertIn(f"mountPath: {raw['home']}", job)
        for repo in raw["repos"]:
            self.assertTrue(repo["path"].startswith("/repos/"),
                            "un chemin de depot doit etre celui vu du pod")

    def test_the_cluster_configuration_rebuilds_context_rather_than_resuming(self) -> None:
        # A claude session is filed under a slug of its working directory, so a pod
        # cannot resume a conversation created anywhere else. "resume" here would
        # not fail loudly: it would start every round from an empty conversation
        # while claiming continuity.
        self.assertEqual(configmap_json()["continuity"], "rebuild")


class ImageNaming(unittest.TestCase):
    def test_compose_and_job_name_the_same_image(self) -> None:
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        job = (ROOT / "k8s" / "30-job.yaml").read_text(encoding="utf-8")
        tag = "forgeron:0.1.0"
        self.assertIn(f"image: {tag}", compose)
        self.assertIn(f"image: {tag}", job)

    def test_the_tag_matches_the_package_version(self) -> None:
        from forgeron import __version__
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn(f"forgeron:{__version__}", compose,
                      "l'etiquette d'image doit suivre la version du paquet")


class Dockerfile(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")

    def test_it_runs_as_a_non_root_user(self) -> None:
        self.assertIn("USER $USERNAME", self.text)
        self.assertIn("useradd", self.text)

    def test_no_secret_is_ever_baked_in(self) -> None:
        # A layer is public once the image is pushed, and a later instruction that
        # deletes a file does not erase the layer before it.
        for forbidden in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "GH_TOKEN",
                          "sk-ant-"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_it_installs_the_commit_msg_hook(self) -> None:
        # Le hook du poste de l'auteur ne suit pas dans l'image. Sans cette ligne
        # la couche qui previent manque exactement la ou l'agent est le moins
        # surveille, et il ne reste que la verification apres coup.
        self.assertIn("forgeron hook --install", self.text)
        self.assertIn("core.hooksPath", self.text)

    def test_the_package_path_it_copies_is_the_one_it_puts_on_pythonpath(self) -> None:
        self.assertIn("COPY --chown=$UID:$GID forgeron/ /opt/forgeron/forgeron/", self.text)
        self.assertIn("PYTHONPATH=/opt/forgeron", self.text)


class Entrypoint(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    def test_it_refuses_to_start_without_any_claude_credential(self) -> None:
        self.assertIn("exit 3", self.text)
        self.assertIn("aucune authentification claude", self.text)

    def test_it_never_prints_a_credential(self) -> None:
        # Saying WHICH mode is active is useful; printing the value is the classic
        # way a token ends up in a log aggregator.
        for line in self.text.splitlines():
            if "echo" in line and "TOKEN" in line:
                self.assertNotIn("${CLAUDE_CODE_OAUTH_TOKEN}", line)
                self.assertNotIn("$CLAUDE_CODE_OAUTH_TOKEN", line)

    def test_it_marks_mounted_repositories_safe_for_git(self) -> None:
        # A volume mounted from the host carries the host's uid, and git refuses to
        # work in a repository owned by someone else: "detected dubious ownership",
        # which reads as a permissions problem and is not one.
        self.assertIn("safe.directory", self.text)


if __name__ == "__main__":
    unittest.main()
