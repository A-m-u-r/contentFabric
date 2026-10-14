"""Offline deployment behavior checks; never talks to Docker or an API."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("deploy.py")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "The deployment helper is not implemented yet")
        spec = importlib.util.spec_from_file_location("home_deployment", SCRIPT)
        self.deployer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.deployer)
        self.temp = tempfile.TemporaryDirectory(prefix="content-fabric-deploy-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "checkout"
        (self.project / "deploy").mkdir(parents=True)
        (self.project / "deploy" / "compose.yml").write_text("new compose\n")
        (self.project / "deploy" / ".env.example").write_text("MAX_CONCURRENT_JOBS=1\n")
        self.destination = self.root / "server"
        self.calls = []

    def run_docker(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    def update(self, run=None, prefix="ghcr.io/owner/content-fabric", tag=None):
        return self.deployer.deploy(
            project_dir=self.project,
            deployment_dir=self.destination,
            image_prefix=prefix,
            image_tag=tag or "b" * 40,
            registry_user="owner",
            registry_token="temporary-registry-token",
            run=run or self.run_docker,
        )

    def make_existing_release(self):
        self.destination.mkdir()
        old_env = "MAX_CONCURRENT_JOBS=1\nOPENSHORTS_KEY_VAULT_SECRET=" + "a" * 64 + "\n"
        (self.destination / ".env").write_text(old_env)
        old_images = "IMAGE_PREFIX=ghcr.io/owner/content-fabric\nIMAGE_TAG=" + "a" * 40 + "\n"
        (self.destination / "images.env").write_text(old_images)
        (self.destination / "compose.yml").write_text("old compose\n")
        (self.destination / "user-data.txt").write_text("existing accounts and videos")
        return old_env, old_images

    def test_first_deploy_creates_private_config_outside_checkout(self):
        self.update()
        env = (self.destination / ".env").read_text()
        self.assertRegex(env, r"OPENSHORTS_KEY_VAULT_SECRET=[0-9a-f]{64}\n")
        self.assertIn("MAX_CONCURRENT_JOBS=1", env)
        self.assertFalse((self.project / ".env").exists())
        self.assertNotIn("temporary-registry-token", env)
        self.assertNotIn("temporary-registry-token", (self.destination / "images.env").read_text())
        self.assertTrue(any("--wait" in command for command, _ in self.calls))
        self.assertFalse(list(self.destination.glob(".registry-auth-*")))

    def test_update_preserves_application_keys_and_user_data(self):
        old_env, _ = self.make_existing_release()
        self.update()
        self.assertEqual(old_env, (self.destination / ".env").read_text())
        self.assertEqual("existing accounts and videos", (self.destination / "user-data.txt").read_text())
        self.assertFalse(any("down" in command for command, _ in self.calls))

    def test_failed_healthcheck_restores_previous_release(self):
        old_env, old_images = self.make_existing_release()
        up_attempts = []

        def fail_first_start(command, **kwargs):
            self.calls.append((command, kwargs))
            if "up" in command:
                up_attempts.append((self.destination / "images.env").read_text())
                if len(up_attempts) == 1:
                    raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with self.assertRaises(self.deployer.DeploymentError):
            self.update(run=fail_first_start)
        self.assertEqual(2, len(up_attempts))
        self.assertEqual(old_images, up_attempts[-1])
        self.assertEqual(old_images, (self.destination / "images.env").read_text())
        self.assertEqual("old compose\n", (self.destination / "compose.yml").read_text())
        self.assertEqual(old_env, (self.destination / ".env").read_text())
        self.assertEqual("existing accounts and videos", (self.destination / "user-data.txt").read_text())
        self.assertFalse(list(self.destination.glob(".registry-auth-*")))

    def test_untrusted_image_metadata_cannot_change_server_files(self):
        old_env, old_images = self.make_existing_release()
        with self.assertRaises(ValueError):
            self.update(prefix="ghcr.io/owner/project\nOTHER_CONFIG=bad")
        self.assertEqual([], self.calls)
        self.assertEqual(old_env, (self.destination / ".env").read_text())
        self.assertEqual(old_images, (self.destination / "images.env").read_text())


if __name__ == "__main__":
    unittest.main()
