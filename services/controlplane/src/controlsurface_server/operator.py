"""Offline, local-only operator recovery commands."""

from __future__ import annotations

import argparse
import getpass
import json
import re

from .auth import reset_owner_password
from .settings import load_settings
from .storage import clickhouse, postgres

_BACKUP_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\.zip$")


def clickhouse_backup(name: str, *, restore: bool = False) -> None:
    if not _BACKUP_NAME.fullmatch(name):
        raise ValueError("Backup name must be an alphanumeric .zip basename")
    settings = load_settings()
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}", settings.clickhouse_database):
        raise ValueError("Configured ClickHouse database is not a safe identifier")
    client = clickhouse(settings)
    try:
        operation = "RESTORE" if restore else "BACKUP"
        direction = "FROM" if restore else "TO"
        client.command(
            f"{operation} DATABASE {settings.clickhouse_database} {direction} "
            f"Disk('controlsurface_backups', '{name}')"
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="controlsurface-operator")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-owner-password", help="Reset owner login; revoke sessions")
    reset.add_argument(
        "--email", required=True, help="Existing owner email, verified before change"
    )
    for command in ("backup-clickhouse", "restore-clickhouse"):
        backup = commands.add_parser(command)
        backup.add_argument("--name", required=True)
    commands.add_parser("inbox-status", help="Inspect queued and dead-letter telemetry batches")
    requeue = commands.add_parser("requeue-dead-letters", help="Retry dead-letter batches")
    requeue.add_argument("--limit", type=int, default=1000)
    requeue.add_argument("--confirm", action="store_true", required=True)
    args = parser.parse_args()

    if args.command == "reset-owner-password":
        password = getpass.getpass("New owner password: ")
        if password != getpass.getpass("Confirm new owner password: "):
            parser.error("Passwords did not match; no changes made")
        if len(password) < 12:
            parser.error("Password must contain at least 12 characters")
        with postgres(load_settings()) as connection:
            reset_owner_password(connection, args.email, password)
        print("Owner password reset; all browser sessions revoked. Project API keys remain valid.")
    elif args.command in {"backup-clickhouse", "restore-clickhouse"}:
        clickhouse_backup(args.name, restore=args.command == "restore-clickhouse")
        print("ClickHouse operation completed")
    elif args.command == "inbox-status":
        with postgres(load_settings()) as connection:
            row = connection.execute(
                "SELECT count(*) FILTER (WHERE processed_at IS NULL AND dead_letter_at IS NULL) "
                "AS pending, count(*) FILTER (WHERE dead_letter_at IS NOT NULL) AS dead, "
                "coalesce(sum(octet_length(payload_zlib)) FILTER "
                "(WHERE processed_at IS NULL AND dead_letter_at IS NULL), 0) AS pending_bytes "
                "FROM telemetry_inbox"
            ).fetchone()
        if row is None:
            raise RuntimeError("Telemetry inbox status query returned no aggregate row")
        print(json.dumps(dict(row)))
    elif args.command == "requeue-dead-letters":
        if not 1 <= args.limit <= 10000:
            parser.error("Limit must be between 1 and 10000")
        with postgres(load_settings()) as connection:
            rows = connection.execute(
                "WITH selected AS (SELECT id FROM telemetry_inbox "
                "WHERE dead_letter_at IS NOT NULL ORDER BY received_at "
                "LIMIT %s FOR UPDATE SKIP LOCKED) "
                "UPDATE telemetry_inbox AS batch SET dead_letter_at = NULL, "
                "attempts = 0, available_at = now(), lease_until = NULL, lease_owner = NULL, "
                "last_error = NULL FROM selected WHERE batch.id = selected.id RETURNING batch.id",
                (args.limit,),
            ).fetchall()
        print(f"Requeued {len(rows)} dead-letter batch(es)")


if __name__ == "__main__":
    main()
