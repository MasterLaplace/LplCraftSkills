"""The Dockerfile and the manifests, checked against the code they deploy.

Neither docker nor kubectl is installed here, so nothing can be built or
applied. But two classes of errors can be checked offline, and they are
precisely the ones that cost the most to discover in a pod:

- a configuration that `config.load()` would refuse. A broken JSON in a ConfigMap
  only shows at container startup, after the build and the push;
- a path or an image name that no longer matches between the Dockerfile, the compose
  file and the Job. It is duplication: three files name the same image.
"""

from __future__ import annotations

import json
import pathlib
import re
import tempfile
import unittest

from forgeron.config import Config, load

ROOT = pathlib.Path(__file__).resolve().parents[1]


def configmap_json() -> dict:
    raw = (ROOT / "k8s" / "20-configmap.yaml").read_text(encoding="utf-8")
    body = raw.split("config.json: |", 1)[1]
    dedented = "\n".join(line[4:] if line.startswith("    ") else line
                         for line in body.splitlines())
    return json.loads(dedented)


def load_through_a_file(raw: dict) -> Config:
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder) / "config.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return load(str(path))


def compose_mount_points() -> set[str]:
    compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*- [^\s:]+:(/[^\s:]+)", compose, re.M))


class ConfigMap(unittest.TestCase):
    def test_the_embedded_configuration_is_one_the_loader_accepts(self) -> None:
        load_through_a_file(configmap_json())

    def test_paths_are_the_ones_the_job_mounts(self) -> None:
        raw = configmap_json()
        job = (ROOT / "k8s" / "30-job.yaml").read_text(encoding="utf-8")
        # `home` is where the state lives and `path` is where a clone is expected;
        # both are paths INSIDE the pod, and a config copied from a laptop names
        # neither. This is the check that catches that.
        self.assertIn(f"mountPath: {raw['home']}", job)
        for repo in raw["repos"]:
            self.assertTrue(repo["path"].startswith("/repos/"),
                            "a repository path must be the one seen from the pod")

    def test_the_cluster_configuration_rebuilds_context_rather_than_resuming(self) -> None:
        # A claude session is filed under a slug of its working directory, so a pod
        # cannot resume a conversation created anywhere else. "resume" here would
        # not fail loudly: it would start every round from an empty conversation
        # while claiming continuity.
        self.assertEqual(configmap_json()["continuity"], "rebuild")

    def test_an_agent_is_named_only_if_the_image_installs_the_pack_and_node(self) -> None:
        dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
        if configmap_json().get("agent", Config().agent):
            self.assertIn("/opt/craft/install.sh", dockerfile)
            self.assertIn("nodejs", dockerfile)


class TheTutorialConfiguration(unittest.TestCase):
    """The tutorial's configuration block, read back by the REAL loader.

    It exists because a reader followed the tutorial to the letter and stopped on
    "config.json missing": the step was not there. Writing it is not enough, since
    prose in a doc drifts in silence. Paired with this test it breaks when it lies.
    """

    def block(self) -> dict:
        text = (ROOT / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")
        found = re.search(r"cat > ~/\.forgeron/config\.json <<'JSON'\n(.*?)\nJSON",
                          text, re.S)
        self.assertIsNotNone(found, "the tutorial no longer carries a configuration block")
        return json.loads(found.group(1))

    def test_the_loader_accepts_it(self) -> None:
        load_through_a_file(self.block())

    def test_the_paths_are_the_ones_the_container_sees(self) -> None:
        # The compose mount decides this path. A host path here and `gh` answers
        # correctly while `git` fails, with nothing that points at the cause.
        mounted = compose_mount_points()
        for repo in self.block()["repos"]:
            self.assertTrue(repo["path"].startswith("/repos/"),
                            "a repository path must be the one seen from the container")
            self.assertIn(repo["path"], mounted,
                          "the tutorial names a path that compose does not mount")

    def test_home_is_left_out_since_it_is_derived_at_run_time(self) -> None:
        # `home` is derived from $HOME at run time: written out, it would break
        # exactly what its absence makes work.
        self.assertNotIn("home", self.block())


class ImageNaming(unittest.TestCase):
    def test_compose_and_job_name_the_same_image(self) -> None:
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        job = (ROOT / "k8s" / "30-job.yaml").read_text(encoding="utf-8")
        tag = "forgeron:0.1.0"
        self.assertIn(f"image: {tag}", compose)
        self.assertIn(f"image: {tag}", job)

    def test_compose_builds_from_the_repository_root(self) -> None:
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        context = next(line.split(":", 1)[1].strip() for line in compose.splitlines()
                       if line.strip().startswith("context:"))
        dockerfile = next(line.split(":", 1)[1].strip() for line in compose.splitlines()
                          if line.strip().startswith("dockerfile:"))
        root = (ROOT / "docker" / context).resolve()
        self.assertTrue((root / "install.sh").is_file(), f"{root} is not the repository root")
        self.assertEqual((root / dockerfile).resolve(), (ROOT / "docker" / "Dockerfile").resolve())

    def test_the_tag_matches_the_package_version(self) -> None:
        from forgeron import __version__
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn(f"forgeron:{__version__}", compose,
                      "the image tag must follow the package version")


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
        # The hook on the author's workstation does not follow into the image. Without
        # this line the layer that prevents is missing exactly where the agent is the
        # least watched, and only the after-the-fact check is left.
        self.assertIn("forgeron hook --install", self.text)
        self.assertIn("core.hooksPath", self.text)

    def test_the_package_path_it_copies_is_the_one_it_puts_on_pythonpath(self) -> None:
        self.assertIn("COPY --chown=$UID:$GID forgeron/forgeron/ /opt/forgeron/forgeron/", self.text)
        self.assertIn("PYTHONPATH=/opt/forgeron", self.text)

    def test_it_installs_the_pack_it_tells_the_agent_to_use(self) -> None:
        for piece in ("skills/ /opt/craft/skills/", "agents/ /opt/craft/agents/",
                      "install.sh /opt/craft/install.sh", "RUN /opt/craft/install.sh"):
            with self.subTest(piece=piece):
                self.assertIn(piece, self.text)

    def test_its_ignore_file_keeps_git_history_out_of_the_context(self) -> None:
        ignore = (ROOT / "docker" / "Dockerfile.dockerignore").read_text(encoding="utf-8")
        self.assertIn(".git", ignore)
        self.assertIn("__pycache__", ignore)


class Entrypoint(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    def test_it_refuses_to_start_without_any_claude_credential(self) -> None:
        self.assertIn("exit 3", self.text)
        self.assertIn("no claude authentication", self.text)

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
