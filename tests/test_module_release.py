"""Verify publication cannot silently move a tested module version."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


class ModuleReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "modules").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy(REPOSITORY / "scripts/publish-module-version.sh", self.root / "scripts")
        (self.root / "modules/VERSION").write_text("0.1.0\n")
        (self.root / "modules/example.tf").write_text('# initial module\n')
        fake_gh = self.root / "bin/gh"
        fake_gh.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" >"$RELEASE_CALL_LOG"\n')
        fake_gh.chmod(0o755)
        self.call_log = self.root / "api-call.txt"
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Release test")
        self.commit()

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git("add", "modules", "scripts")
        self.git("commit", "-qm", "test module version")
        return self.git("rev-parse", "HEAD")

    def publish(self, commit=None):
        environment = dict(os.environ,
                           PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"],
                           RELEASE_CALL_LOG=str(self.call_log),
                           GITHUB_REPOSITORY="MichalBoczula/ECommerceStore.Infrastructure",
                           GITHUB_EVENT_NAME="workflow_run",
                           MODULE_RELEASE_COMMIT=commit or self.git("rev-parse", "HEAD"))
        return subprocess.run(["bash", "scripts/publish-module-version.sh"],
                              cwd=self.root, env=environment, capture_output=True, text=True)

    def test_new_version_targets_the_tested_commit(self):
        commit = self.git("rev-parse", "HEAD")
        result = self.publish(commit)
        self.assertEqual(0, result.returncode, result.stderr)
        call = self.call_log.read_text().splitlines()
        self.assertEqual(["api", "--method", "POST",
                          "repos/MichalBoczula/ECommerceStore.Infrastructure/git/refs",
                          "-f", "ref=refs/tags/modules-v0.1.0", "-f", "sha=" + commit], call)

    def test_existing_version_is_retained_for_identical_modules(self):
        self.git("tag", "modules-v0.1.0")
        (self.root / "README.md").write_text("new documentation\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "unrelated root change")
        result = self.publish()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.call_log.exists())

    def test_changed_module_requires_a_version_bump(self):
        self.git("tag", "modules-v0.1.0")
        original = self.git("rev-parse", "modules-v0.1.0")
        (self.root / "modules/example.tf").write_text('# changed module\n')
        self.commit()
        result = self.publish()
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.call_log.exists())
        self.assertEqual(original, self.git("rev-parse", "modules-v0.1.0"))

    def test_unverified_commit_is_rejected(self):
        result = self.publish("0" * 40)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.call_log.exists())


if __name__ == "__main__":
    unittest.main()
