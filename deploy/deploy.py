"""Pull a tested release on the home runner; keep runtime data outside checkout."""
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


class DeploymentError(RuntimeError):
    pass


def atomic_write(path, data):
    temporary = path.with_name(path.name + ".updating")
    temporary.write_bytes(data)
    temporary.replace(path)


def deploy(*, project_dir, deployment_dir, image_prefix, image_tag,
           registry_user, registry_token, run=subprocess.run):
    if not re.fullmatch(r"ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*", image_prefix):
        raise ValueError("IMAGE_PREFIX must be a lowercase GHCR repository name")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", image_tag):
        raise ValueError("IMAGE_TAG must be a full commit hash")
    if not registry_user or not registry_token:
        raise ValueError("The workflow registry credentials are missing")
    destination = Path(deployment_dir).expanduser()
    if not destination.is_absolute():
        raise ValueError("CONTENT_FABRIC_DEPLOY_DIR must be an absolute persistent path")
    destination = destination.resolve()
    checkout = Path(project_dir).resolve()
    if destination == checkout or checkout in destination.parents or destination in checkout.parents:
        raise ValueError("Keep deployment data separate from the runner checkout")
    source = checkout / "deploy"
    compose_source = (source / "compose.yml").read_bytes()
    template = (source / ".env.example").read_text(encoding="utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    app_env = destination / ".env"
    if not app_env.exists():
        lines = [line for line in template.splitlines()
                 if not line.startswith("OPENSHORTS_KEY_VAULT_SECRET=")]
        lines.append("OPENSHORTS_KEY_VAULT_SECRET=" + secrets.token_hex(32))
        # Exclusive creation prevents a second run from overwriting user settings.
        fd = os.open(app_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

    images = destination / "images.env"
    compose = destination / "compose.yml"
    previous_images = images.read_bytes() if images.exists() else None
    previous_compose = compose.read_bytes() if compose.exists() else None
    new_images = f"IMAGE_PREFIX={image_prefix}\nIMAGE_TAG={image_tag}\n".encode("ascii")

    with tempfile.TemporaryDirectory(prefix=".registry-auth-", dir=destination) as auth_dir:
        auth_path = Path(auth_dir).resolve()
        if auth_path.parent != destination:
            raise ValueError("Registry configuration must stay inside the deployment directory")
        docker = ["docker", "--config", str(auth_path)]
        command = docker + ["compose", "-p", "content-fabric", "--env-file",
                            str(images), "-f", str(compose)]
        run(docker + ["login", "ghcr.io", "--username", registry_user, "--password-stdin"],
            input=registry_token + "\n", text=True, check=True)
        atomic_write(compose, compose_source)
        atomic_write(images, new_images)
        update_started = False
        try:
            run(command + ["config", "--quiet"], check=True)
            # Pull completes before existing containers are replaced.
            run(command + ["pull"], check=True)
            update_started = True
            run(command + ["up", "-d", "--wait", "--wait-timeout", "240"], check=True)
        except subprocess.CalledProcessError as error:
            if previous_images is not None and previous_compose is not None:
                atomic_write(images, previous_images)
                atomic_write(compose, previous_compose)
                if update_started:
                    try:
                        run(command + ["up", "-d", "--wait", "--wait-timeout", "240"], check=True)
                    except subprocess.CalledProcessError as rollback_error:
                        raise DeploymentError("Update and rollback failed; inspect containers on the server") from rollback_error
                raise DeploymentError("Update failed; previous release configuration restored") from error
            raise DeploymentError("First deployment failed; configuration and data have been preserved") from error
    print("Deployment is healthy. Open http://localhost:5175 on the server.")


def main():
    location = os.environ.get("CONTENT_FABRIC_DEPLOY_DIR", "")
    if not location:
        raise ValueError("Set repository variable CONTENT_FABRIC_DEPLOY_DIR")
    deploy(
        project_dir=Path(__file__).resolve().parent.parent,
        deployment_dir=Path(location),
        image_prefix=os.environ.get("IMAGE_PREFIX", ""),
        image_tag=os.environ.get("IMAGE_TAG", ""),
        registry_user=os.environ.get("GHCR_USER", ""),
        registry_token=os.environ.get("GHCR_TOKEN", ""),
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, DeploymentError, subprocess.CalledProcessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
