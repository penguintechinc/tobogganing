"""Command-line interface for backup operations."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

from .manager import BackupManager

logger = logging.getLogger(__name__)


async def _async_backup_cli(db: Any, args: Any) -> None:
    """Async implementation of backup CLI commands.

    create/restore accept ``--tenant-id`` to scope the operation to one
    tenant's rows; omitting it performs a whole-DB operation, which is
    reserved for platform operators with shell access to the hub.

    Backup/restore is CLI- and scheduler-worker-only: no HTTP route exposes
    it. Any future HTTP route MUST require platform-admin scope for whole-DB
    operations and tenant-matched scope for tenant-scoped ones.

    Args:
        db: penguin-dal AsyncDB instance
        args: Parsed command-line arguments
    """
    manager = BackupManager(db)

    if args.command == "create":
        result = await manager.create_backup(
            backup_name=args.name,
            compress=args.compress,
            encrypt=args.encrypt,
            encryption_key=args.key,
            upload_to_s3=args.s3,
            tenant_id=args.tenant_id,
        )
        print(f"Backup created: {result['file_path']}")
        if result.get("s3_info"):
            print(f"Uploaded to S3: {result['s3_info']['s3_key']}")

    elif args.command == "restore":
        result = await manager.restore_backup(
            backup_path=args.path,
            decrypt=args.decrypt,
            decryption_key=args.key,
            from_s3=args.from_s3,
            tenant_id=args.tenant_id,
            allow_scope_mismatch=args.allow_scope_mismatch,
        )
        print(f"Restore completed: {result['total_rows_restored']} rows")

    elif args.command == "list":
        if args.s3_only:
            if manager.s3_manager:
                backups = manager.s3_manager.list_backups()
            else:
                backups = []
        elif args.local_only:
            backups = manager.list_backups(include_s3=False)
        else:
            backups = manager.list_backups(include_s3=True)

        for backup in backups:
            location = backup.get("storage_location", "unknown")
            name = backup.get("backup_name", "unknown")
            created = backup.get("created_at", "unknown")
            print(f"- {name} ({created}) [{location}]")

    elif args.command == "delete":
        if manager.delete_backup(args.name, from_s3=args.from_s3):
            print(f"Backup deleted: {args.name}")
        else:
            print(f"Backup not found: {args.name}")

    elif args.command == "migrate-global-prefix":
        if not manager.s3_manager:
            raise RuntimeError("S3 not configured")
        report = manager.s3_manager.migrate_global_prefix(dry_run=args.dry_run)
        verb = "Would move" if args.dry_run else "Moved"
        print(
            f"{verb} {len(report['backups'])} whole-DB backups "
            f"({report['moved']} objects moved, {report['examined']} keys examined)"
        )

    elif args.command == "s3-status":
        config = manager.s3_config
        print(f"S3 Enabled: {config.enabled}")
        if config.enabled:
            print(f"Bucket: {config.bucket}")
            print(f"Region: {config.region}")
            print(f"Endpoint: {config.endpoint_url or 'Default AWS'}")
            print(f"Connected: {manager.s3_manager is not None}")

            if manager.s3_manager and manager.s3_manager.client:
                try:
                    manager.s3_manager.client.head_bucket(Bucket=config.bucket)
                    print("Connection Test: ✓ Success")
                except Exception as e:
                    print(f"Connection Test: ✗ Failed ({e})")

    else:
        raise ValueError(f"unknown command: {args.command}")


def backup_cli(db: Any, get_db_uri_fn: Any | None = None) -> None:
    """Command-line interface for backup operations.

    Args:
        db: penguin-dal AsyncDB instance
        get_db_uri_fn: Optional function to get database URI
    """
    parser = argparse.ArgumentParser(description="SASEWaddle Database Backup Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create backup
    backup_parser = subparsers.add_parser("create", help="Create backup")
    backup_parser.add_argument("--name", help="Backup name")
    backup_parser.add_argument("--compress", action="store_true", help="Compress backup")
    backup_parser.add_argument("--encrypt", action="store_true", help="Encrypt backup")
    backup_parser.add_argument("--key", help="Encryption key")
    backup_parser.add_argument("--s3", action="store_true", help="Upload to S3")
    backup_parser.add_argument(
        "--tenant-id", default=None, help="Scope backup to this tenant (default: whole DB)"
    )

    # Restore backup
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("path", help="Backup path or S3 key")
    restore_parser.add_argument("--decrypt", action="store_true", help="Decrypt backup")
    restore_parser.add_argument("--key", help="Decryption key")
    restore_parser.add_argument("--from-s3", action="store_true", help="Restore from S3")
    restore_parser.add_argument(
        "--tenant-id", default=None, help="Scope restore to this tenant (default: whole DB)"
    )
    restore_parser.add_argument(
        "--allow-scope-mismatch",
        action="store_true",
        help="Restore into --tenant-id even if the backup's declared scope differs",
    )

    # List backups
    list_parser = subparsers.add_parser("list", help="List backups")
    list_parser.add_argument("--local-only", action="store_true", help="List only local")
    list_parser.add_argument("--s3-only", action="store_true", help="List only S3")

    # Delete backup
    delete_parser = subparsers.add_parser("delete", help="Delete backup")
    delete_parser.add_argument("name", help="Backup name")
    delete_parser.add_argument("--from-s3", action="store_true", help="Delete from S3")

    # S3 status
    subparsers.add_parser("s3-status", help="Check S3 configuration")

    migrate_parser = subparsers.add_parser(
        "migrate-global-prefix", help="Move legacy root whole-DB S3 backups into _global/"
    )
    migrate_parser.add_argument("--dry-run", action="store_true", help="Report only")

    args = parser.parse_args()

    try:
        asyncio.run(_async_backup_cli(db, args))
    except Exception as e:
        logger.error(f"CLI error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Stub for direct execution
    print("Use backup_cli(db, get_db_uri_fn) from application context")
    sys.exit(1)
