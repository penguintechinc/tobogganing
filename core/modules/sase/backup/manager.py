"""Database backup manager for local and S3 storage."""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from .crypto import decrypt_file, encrypt_file
from .s3 import S3Config, S3Manager

logger = structlog.get_logger()

# Strict allowlist pattern for backup names: alphanumeric, dots, hyphens, underscores
VALID_BACKUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_backup_name(backup_name: str) -> None:
    """
    Validate backup name against path traversal and injection attacks.

    Args:
        backup_name: Backup name to validate

    Raises:
        ValueError: If name is invalid or contains suspicious patterns
    """
    if not backup_name or len(backup_name) > 255:
        raise ValueError("Backup name must be 1-255 characters")

    if ".." in backup_name or backup_name.startswith("/"):
        raise ValueError("Backup name cannot contain '..' or start with '/'")

    if not VALID_BACKUP_NAME_PATTERN.match(backup_name):
        raise ValueError(
            "Backup name must contain only alphanumeric, dots, hyphens, underscores"
        )


def _validate_path_in_directory(file_path: Path, base_dir: Path) -> Path:
    """
    Validate that a path resolves within a base directory.

    Args:
        file_path: Path to validate
        base_dir: Base directory that file_path must be within

    Returns:
        Resolved file path

    Raises:
        ValueError: If file_path is outside base_dir or is a symlink
    """
    # Reject symlinks first (prevent escape via symlinks)
    if file_path.is_symlink():
        raise ValueError("Symlinks not allowed in backup operations")

    try:
        # Resolve paths to absolute
        resolved_file = file_path.resolve()
        resolved_base = base_dir.resolve()

        # Check if file is within base directory
        resolved_file.relative_to(resolved_base)

        return resolved_file
    except ValueError as e:
        if "is not in the subpath of" in str(e):
            raise ValueError(f"Path escapes backup directory: {file_path}") from e
        raise


class BackupManager:
    """Manages database backup and restore operations."""

    def __init__(
        self, db: Any, backup_dir: str = "/backups", get_db_uri_fn: Any | None = None
    ) -> None:
        """Initialize backup manager.

        Args:
            db: penguin-dal AsyncDB instance
            backup_dir: Directory for local backups
            get_db_uri_fn: Optional function to get database URI
        """
        self.db: Any = db
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.get_db_uri_fn = get_db_uri_fn

        self.s3_config = S3Config.from_env()
        self.s3_manager: S3Manager | None = None

        if self.s3_config.enabled:
            self.s3_manager = S3Manager(self.s3_config)

    async def create_backup(
        self,
        backup_name: str | None = None,
        compress: bool = True,
        encrypt: bool = False,
        encryption_key: str | None = None,
        upload_to_s3: bool | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a full database backup.

        Args:
            backup_name: Custom backup name (auto-generated if not provided)
            compress: Whether to compress backup
            encrypt: Whether to encrypt backup
            encryption_key: Encryption key (required if encrypt=True)
            upload_to_s3: Override S3 upload setting
            tenant_id: Tenant ID for multi-tenant isolation (scopes backup)

        Returns:
            Backup metadata dict

        Raises:
            ValueError: If backup_name is invalid or tenant is unauthorized
        """
        try:
            if not backup_name:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_name = f"sasewaddle_backup_{timestamp}"
            else:
                # Validate backup name to prevent path traversal
                _validate_backup_name(backup_name)

            ext = ".json"
            if compress:
                ext += ".gz"
            if encrypt:
                ext += ".enc"

            # Build path with tenant isolation if provided
            if tenant_id:
                _validate_backup_name(tenant_id)  # Validate tenant_id too
                backup_file = self.backup_dir / tenant_id / f"{backup_name}{ext}"
                backup_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                backup_file = self.backup_dir / f"{backup_name}{ext}"

            # Validate path is within backup directory
            _validate_path_in_directory(backup_file, self.backup_dir)

            # Export all tables
            backup_data: dict[str, Any] = {
                "metadata": {
                    "version": "1.0",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "db_uri": self._sanitize_db_uri(),
                    "tables": [],
                },
                "data": {},
            }

            # Backup each table from DAL
            for table_name in self.db.tables:
                try:
                    table = getattr(self.db, table_name)
                    rows = await self.db(table).select()

                    table_data: list[dict[str, Any]] = []
                    for row in rows:
                        row_dict: dict[str, Any] = row.as_dict()
                        # Convert datetime objects to ISO format strings
                        for key, value in row_dict.items():
                            if isinstance(value, datetime):
                                row_dict[key] = value.isoformat()
                        table_data.append(row_dict)

                    backup_data["data"][table_name] = table_data
                    backup_data["metadata"]["tables"].append(
                        {"name": table_name, "row_count": len(table_data)}
                    )
                except Exception as e:
                    logger.warning("failed_to_backup_table", table_name=table_name, error=str(e))

            # Write JSON (compressed if requested)
            json_data = json.dumps(backup_data, indent=2)
            if compress:
                json_bytes = json_data.encode("utf-8")
                with gzip.open(backup_file, "wb") as f:
                    f.write(json_bytes)
            else:
                with open(backup_file, "w") as f:
                    f.write(json_data)

            # Encrypt if requested
            if encrypt:
                if not encryption_key:
                    raise ValueError("Encryption key required")
                backup_file = encrypt_file(backup_file, encryption_key)

            # Calculate checksum
            checksum = self._calculate_checksum(backup_file)

            # Upload to S3 if enabled
            s3_info: Optional[Dict[str, Any]] = None
            should_upload_s3 = (
                upload_to_s3 if upload_to_s3 is not None else self.s3_config.enabled
            )

            if should_upload_s3 and self.s3_manager:
                s3_info = self.s3_manager.upload_backup(backup_file, backup_name)

            # Create metadata
            metadata: dict[str, Any] = {
                "backup_name": backup_name,
                "file_path": str(backup_file),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "compressed": compress,
                "encrypted": encrypt,
                "checksum": checksum,
                "size_bytes": backup_file.stat().st_size,
                "table_count": len(backup_data["metadata"]["tables"]),
                "total_rows": sum(t["row_count"] for t in backup_data["metadata"]["tables"]),
                "s3_info": s3_info,
            }

            # Save metadata
            metadata_file = backup_file.with_suffix(".meta")
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

            if s3_info and self.s3_manager:
                self.s3_manager.upload_metadata(metadata_file, backup_name)

            logger.info("backup_created", backup_file=str(backup_file))
            if s3_info:
                logger.info("uploaded_to_s3", s3_key=s3_info["s3_key"])

            return metadata

        except Exception as e:
            logger.error("backup_failed", error=str(e))
            raise

    async def restore_backup(
        self,
        backup_path: str,
        decrypt: bool = False,
        decryption_key: str | None = None,
        verify_checksum: bool = True,
        from_s3: bool = False,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Restore database from backup.

        Args:
            backup_path: Path to backup file or S3 key
            decrypt: Whether to decrypt backup
            decryption_key: Decryption key (required if decrypt=True)
            verify_checksum: Whether to verify integrity
            from_s3: Whether to download from S3 first
            tenant_id: Tenant ID for multi-tenant isolation (validates authorization)

        Returns:
            Restore statistics dict

        Raises:
            ValueError: If path escapes backup directory or tenant is unauthorized
        """
        try:
            # Handle S3 download
            if from_s3 and self.s3_manager:
                backup_file = self.s3_manager.download_backup(backup_path)
            else:
                backup_file = Path(backup_path)
                if not backup_file.exists():
                    raise FileNotFoundError(f"Backup not found: {backup_file}")

                # Validate path is within backup directory
                _validate_path_in_directory(backup_file, self.backup_dir)

                # If tenant_id provided, verify backup belongs to that tenant
                if tenant_id:
                    _validate_backup_name(tenant_id)
                    tenant_dir = self.backup_dir / tenant_id
                    if tenant_dir.exists():
                        _validate_path_in_directory(backup_file, tenant_dir)

            # Load and verify metadata
            metadata_file = backup_file.with_suffix(".meta")
            if metadata_file.exists():
                with open(metadata_file, "r") as f:
                    metadata = json.load(f)

                if verify_checksum and "checksum" in metadata:
                    actual_checksum = self._calculate_checksum(backup_file)
                    if actual_checksum != metadata["checksum"]:
                        raise ValueError("Checksum verification failed")

            # Decrypt if needed
            if decrypt:
                if not decryption_key:
                    raise ValueError("Decryption key required")
                backup_file = decrypt_file(backup_file, decryption_key)

            # Decompress and load
            if backup_file.suffix == ".gz":
                with gzip.open(backup_file, "rb") as f:
                    json_data = f.read().decode("utf-8")
            else:
                with open(backup_file, "r") as f:
                    json_data = f.read()

            backup_data = json.loads(json_data)

            if "metadata" not in backup_data or "data" not in backup_data:
                raise ValueError("Invalid backup format")

            # Restore
            restore_stats: dict[str, Any] = {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "tables_restored": [],
                "total_rows_restored": 0,
                "errors": [],
            }

            for table_name, table_data in backup_data["data"].items():
                try:
                    if table_name not in self.db.tables:
                        logger.warning("table_not_found", table_name=table_name)
                        restore_stats["errors"].append(f"Table {table_name} not found")
                        continue

                    table = getattr(self.db, table_name)
                    await self.db(table).delete()

                    rows_restored = 0
                    for row_data in table_data:
                        # Convert ISO datetime strings back to datetime objects
                        for field, value in list(row_data.items()):
                            if isinstance(value, str) and field.endswith("_at"):
                                try:
                                    row_data[field] = datetime.fromisoformat(value)
                                except (ValueError, TypeError):
                                    pass  # Keep original if not a valid datetime

                        await table.async_insert(**row_data)
                        rows_restored += 1

                    restore_stats["tables_restored"].append(
                        {"name": table_name, "rows": rows_restored}
                    )
                    restore_stats["total_rows_restored"] += rows_restored

                    logger.info("restored_rows", table_name=table_name, rows=rows_restored)

                except Exception as e:
                    logger.error("restore_table_failed", table_name=table_name, error=str(e))
                    restore_stats["errors"].append(f"Table {table_name}: {str(e)}")

            restore_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "restore_completed", total_rows_restored=restore_stats["total_rows_restored"]
            )

            return restore_stats

        except Exception as e:
            logger.error("restore_failed", error=str(e))
            raise

    def list_backups(
        self, include_s3: bool = True, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        List all backups.

        Args:
            include_s3: Whether to include S3 backups
            tenant_id: Optional tenant ID to filter backups to single tenant

        Returns:
            List of backup metadata dicts

        Raises:
            ValueError: If tenant_id is invalid
        """
        backups: list[dict[str, Any]] = []

        if tenant_id:
            _validate_backup_name(tenant_id)
            backup_search_dir = self.backup_dir / tenant_id
        else:
            backup_search_dir = self.backup_dir

        # Local backups
        for meta_file in backup_search_dir.glob("**/*.meta"):
            try:
                # Validate meta file is within the search directory
                _validate_path_in_directory(meta_file, backup_search_dir)
                with open(meta_file, "r") as f:
                    metadata = json.load(f)
                    metadata["storage_location"] = "local"
                    if tenant_id:
                        metadata["tenant_id"] = tenant_id
                    backups.append(metadata)
            except Exception as e:
                logger.warning("could_not_read_meta_file", meta_file=str(meta_file), error=str(e))

        # S3 backups
        if include_s3 and self.s3_manager:
            s3_backups = self.s3_manager.list_backups()
            for s3_backup in s3_backups:
                s3_backup["storage_location"] = "s3"
                s3_metadata = self.s3_manager.get_metadata(s3_backup["backup_name"])
                if s3_metadata:
                    s3_metadata.update(s3_backup)
                    backups.append(s3_metadata)
                else:
                    s3_backup.update(
                        {
                            "created_at": s3_backup["last_modified"],
                            "compressed": s3_backup["filename"].endswith(".gz"),
                            "encrypted": s3_backup["filename"].endswith(".enc"),
                        }
                    )
                    backups.append(s3_backup)

        # Remove duplicates (prefer S3)
        seen_names: set[str] = set()
        unique_backups: list[dict[str, Any]] = []
        for backup in sorted(
            backups,
            key=lambda x: (x.get("created_at", ""), x.get("storage_location") == "s3"),
            reverse=True,
        ):
            name = backup.get("backup_name")
            if name not in seen_names:
                seen_names.add(name)
                unique_backups.append(backup)

        return unique_backups

    def delete_backup(
        self, backup_name: str, from_s3: bool = False, tenant_id: Optional[str] = None
    ) -> bool:
        """
        Delete a backup.

        Args:
            backup_name: Backup name (must match strict validation)
            from_s3: Whether to delete from S3
            tenant_id: Optional tenant ID for multi-tenant isolation

        Returns:
            True if deleted

        Raises:
            ValueError: If backup_name or tenant_id is invalid or path escapes directory
        """
        # Validate input to prevent path traversal
        _validate_backup_name(backup_name)

        if from_s3 and self.s3_manager:
            return self.s3_manager.delete_backup(backup_name)

        if tenant_id:
            _validate_backup_name(tenant_id)
            delete_dir = self.backup_dir / tenant_id
        else:
            delete_dir = self.backup_dir

        deleted = False
        # Delete backup files that match the backup name with allowed extensions
        # and any associated .meta files
        extensions = ["", ".json", ".json.gz", ".json.gz.enc"]
        for ext in extensions:
            backup_file = delete_dir / f"{backup_name}{ext}"

            if backup_file.exists():
                try:
                    _validate_path_in_directory(backup_file, delete_dir)
                    if backup_file.is_symlink():
                        logger.warning("skipping_symlink", backup_file=str(backup_file))
                        continue
                    backup_file.unlink()
                    logger.info("deleted_backup_file", backup_file=str(backup_file))
                    deleted = True

                    # Delete associated .meta file
                    meta_file = backup_file.parent / f"{backup_file.name}.meta"
                    if meta_file.exists():
                        _validate_path_in_directory(meta_file, delete_dir)
                        if not meta_file.is_symlink():
                            meta_file.unlink()
                            logger.info("deleted_meta_file", meta_file=str(meta_file))
                except ValueError as e:
                    logger.error("delete_failed_path_validation", backup_file=str(backup_file), error=str(e))
                except Exception as e:
                    logger.error("delete_failed", backup_file=str(backup_file), error=str(e))

        # Also clean up any orphaned .meta files matching this backup name
        try:
            for meta_file in delete_dir.glob(f"{backup_name}*.meta"):
                _validate_path_in_directory(meta_file, delete_dir)
                if not meta_file.is_symlink() and meta_file.exists():
                    meta_file.unlink()
                    logger.info("deleted_orphaned_metadata", meta_file=str(meta_file))
                    deleted = True
        except Exception as e:
            logger.error("failed_to_clean_metadata_files", error=str(e))

        return deleted

    def schedule_backup(self, cron_expression: str, **backup_kwargs: Any) -> str:
        """Schedule automatic backups.

        Args:
            cron_expression: Cron expression
            **backup_kwargs: create_backup arguments

        Returns:
            Schedule ID
        """
        # Placeholder for scheduler integration
        schedule_id = f"schedule_{datetime.now(timezone.utc).timestamp()}"
        logger.info("scheduled_backup", schedule_id=schedule_id, cron_expression=cron_expression)
        return schedule_id

    def _sanitize_db_uri(self) -> str:
        """Remove sensitive info from database URI."""
        if self.get_db_uri_fn:
            uri = self.get_db_uri_fn()
        else:
            uri = "unknown"

        return re.sub(r"://[^:]+:[^@]+@", "://***:***@", uri)

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
