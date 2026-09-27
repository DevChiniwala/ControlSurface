"""Coordinated local Compose backup and fresh-project restore.

Run from a trusted operator machine. Backup directories contain sensitive telemetry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

# Docker/Compose is invoked with validated argv and never through a shell.
REPO = Path(__file__).resolve().parents[1]
BACKUP_FILES = ("postgres.dump", "clickhouse.zip")
PROJECT = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def command(
    *args: str, stdout: int | IO[bytes] = subprocess.PIPE
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(  # nosec B603
        args, cwd=REPO, stdout=stdout, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Command failed ({' '.join(args[:4])}): {error}")
    return result


def compose(project: str, overrides: list[Path], *args: str) -> tuple[str, ...]:
    result = ["docker", "compose", "-p", project, "-f", str(REPO / "compose.yaml")]
    for override in overrides:
        result.extend(("-f", str(override)))
    return (*result, *args)


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(project: str, overrides: list[Path], destination: Path) -> None:
    if destination.exists():
        raise ValueError("Backup destination already exists; use a new directory")
    try:
        destination.relative_to(REPO)
    except ValueError:
        pass
    else:
        raise ValueError("Backup destination must be outside the repository")
    destination.mkdir(parents=True)
    archive_name = f"controlsurface-{uuid.uuid4().hex}.zip"
    stopped = False
    try:
        command(*compose(project, overrides, "stop", "web", "api", "ingest", "worker"))
        stopped = True
        with (destination / "postgres.dump").open("wb") as output:
            command(
                *compose(
                    project,
                    overrides,
                    "exec",
                    "-T",
                    "postgres",
                    "pg_dump",
                    "-U",
                    "controlsurface",
                    "-d",
                    "controlsurface",
                    "-Fc",
                ),
                stdout=output,
            )
        command(*compose(project, overrides, "build", "migrate"))
        command(
            *compose(
                project,
                overrides,
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                "python",
                "-m",
                "controlsurface_server.operator",
                "backup-clickhouse",
                "--name",
                archive_name,
            )
        )
        command(
            *compose(
                project,
                overrides,
                "cp",
                f"clickhouse:/backups/{archive_name}",
                str(destination / "clickhouse.zip"),
            )
        )
        manifest = {
            "format": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source_project": project,
            "files": {name: checksum(destination / name) for name in BACKUP_FILES},
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        command(
            *compose(
                project,
                overrides,
                "exec",
                "-T",
                "clickhouse",
                "rm",
                f"/backups/{archive_name}",
            )
        )
    finally:
        if stopped:
            command(
                *compose(
                    project, overrides, "up", "-d", "api", "ingest", "worker", "web"
                )
            )
    print(f"Verified backup written to {destination}. Protect it as sensitive data.")


def restore(project: str, overrides: list[Path], source: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Unsupported backup manifest format")
    for name in BACKUP_FILES:
        if checksum(source / name) != manifest.get("files", {}).get(name):
            raise ValueError(f"Backup checksum mismatch: {name}")
    containers = command(
        *compose(project, overrides, "ps", "-a", "--quiet")
    ).stdout.strip()
    volumes = command(
        "docker",
        "volume",
        "ls",
        "--quiet",
        "--filter",
        f"label=com.docker.compose.project={project}",
    ).stdout.strip()
    if containers or volumes:
        raise ValueError(
            "Restore target must be a new Compose project with no containers or volumes"
        )

    command(
        *compose(project, overrides, "up", "-d", "--wait", "postgres", "clickhouse")
    )
    command(*compose(project, overrides, "build", "migrate"))
    command(
        *compose(
            project,
            overrides,
            "cp",
            str(source / "clickhouse.zip"),
            "clickhouse:/backups/clickhouse.zip",
        )
    )
    command(
        *compose(
            project,
            overrides,
            "run",
            "--rm",
            "--no-deps",
            "migrate",
            "python",
            "-m",
            "controlsurface_server.operator",
            "restore-clickhouse",
            "--name",
            "clickhouse.zip",
        )
    )
    with (source / "postgres.dump").open("rb") as backup_file:
        result = subprocess.run(  # nosec B603
            compose(
                project,
                overrides,
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "-U",
                "controlsurface",
                "-d",
                "controlsurface",
            ),
            cwd=REPO,
            stdin=backup_file,
            capture_output=True,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(
            "PostgreSQL restore failed; do not start application services. "
            + result.stderr.decode("utf-8", errors="replace")
        )
    command(*compose(project, overrides, "up", "--build", "-d", "--wait"))
    print(
        f"Restored to fresh project {project}; inspect /health/ready and validate counts."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--project", default="controlsurface")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--override", action="append", type=Path, default=[])
    args = parser.parse_args()
    if not PROJECT.fullmatch(args.project):
        parser.error("Project must match [a-z][a-z0-9_-]{1,63}")
    overrides = [path.resolve(strict=True) for path in args.override]
    directory = args.directory.resolve()
    try:
        if args.operation == "backup":
            backup(args.project, overrides, directory)
        else:
            restore(args.project, overrides, directory)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Recovery operation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
