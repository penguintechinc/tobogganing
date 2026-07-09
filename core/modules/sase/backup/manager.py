"""Database backup manager for local and S3 storage."""

import gzip
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .crypto import decrypt_file, encrypt_file
from .s3 import S3Config, S3Manager

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages database backup and restore operations."""

    def __init__(
        self, db: Any, backup_dir: str = "/backups", get_db_uri_fn: Optional[Any] = None
    ) -> None:
        """
        Initialize backup manager.

        Args:
            db: penguin-dal DAL instance
            backup_dir: Directory for local backups
            get_db_uri_fn: Optional function to get database URI
        """
        self.db: Any = db
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.get_db_uri_fn = get_db_uri_fn

        self.s3_config = S3Config.from_env()
        self.s3_manager: Optional[S3Manager] = None

        if self.s3_config.enabled:
            self.s3_manager = S3Manager(self.s3_config)

    def create_backup(
        self,
        backup_name: Optional[str] = None,
        compress: bool = True,
        encrypt: bool = False,
        encryption_key: Optional[str] = None,
        upload_to_s3: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Create a full database backup.

        Args:
            backup_name: Custom backup name (auto-generated if not provided)
            compress: Whether to compress backup
            encrypt: Whether to encrypt backup
            encryption_key: Encryption key (required if encrypt=True)
            upload_to_s3: Override S3 upload setting

        Returns:
            Backup metadata dict
        """
        try:
            if not backup_name:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_name = f"sasewaddle_backup_{timestamp}"

            ext = ".json"
            if compress:
                ext += ".gz"
            if encrypt:
                ext += ".enc"

            backup_file = self.backup_dir / f"{backup_name}{ext}"

            # Export all tables
            backup_data: Dict[str, Any] = {
                "metadata": {
                    "version": "1.0",
                    "created_at": datetime.utcnow().isoformat(),
                    "db_uri": self._sanitize_db_uri(),
                    "tables": [],
                },
                "data": {},
            }

            # Backup each table from DAL
            for table_name in self.db.tables:
                table = self.db[table_name]
                rows = self.db(table).select()

                table_data: List[Dict[str, Any]] = []
                for row in rows:
                    row_dict: Dict[str, Any] = {}
                    for field in table.fields:
                        value = row[field]
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        row_dict[field] = value
                    table_data.append(row_dict)

                backup_data["data"][table_name] = table_data
                backup_data["metadata"]["tables"].append(
                    {"name": table_name, "row_count": len(table_data)}
                )

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
            metadata: Dict[str, Any] = {
                "backup_name": backup_name,
                "file_path": str(backup_file),
                "created_at": datetime.utcnow().isoformat(),
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

            if s3_info:
                self.s3_manager.upload_metadata(metadata_file, backup_name)

            logger.info(f"Backup created: {backup_file}")
            if s3_info:
                logger.info(f"Uploaded to S3: {s3_info['s3_key']}")

            return metadata

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise

    def restore_backup(
        self,
        backup_path: str,
        decrypt: bool = False,
        decryption_key: Optional[str] = None,
        verify_checksum: bool = True,
        from_s3: bool = False,
    ) -> Dict[str, Any]:
        """
        Restore database from backup.

        Args:
            backup_path: Path to backup file or S3 key
            decrypt: Whether to decrypt backup
            decryption_key: Decryption key (required if decrypt=True)
            verify_checksum: Whether to verify integrity
            from_s3: Whether to download from S3 first

        Returns:
            Restore statistics dict
        """
        try:
            # Handle S3 download
            if from_s3 and self.s3_manager:
                backup_file = self.s3_manager.download_backup(backup_path)
            else:
                backup_file = Path(backup_path)
                if not backup_file.exists():
                    raise FileNotFoundError(f"Backup not found: {backup_file}")

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
            restore_stats: Dict[str, Any] = {
                "started_at": datetime.utcnow().isoformat(),
                "tables_restored": [],
                "total_rows_restored": 0,
                "errors": [],
            }

            for table_name, table_data in backup_data["data"].items():
                try:
                    if table_name not in self.db.tables:
                        logger.warning(f"Table not found: {table_name}")
                        restore_stats["errors"].append(f"Table {table_name} not found")
                        continue

                    table = self.db[table_name]
                    self.db(table).delete()

                    rows_restored = 0
                    for row_data in table_data:
                        for field, value in row_data.items():
                            if field in table.fields:
                                field_type = table[field].type
                                if field_type == "datetime" and value:
                                    row_data[field] = datetime.fromisoformat(value)

                        table.insert(**row_data)
                        rows_restored += 1

                    self.db.commit()

                    restore_stats["tables_restored"].append(
                        {"name": table_name, "rows": rows_restored}
                    )
                    restore_stats["total_rows_restored"] += rows_restored

                    logger.info(f"Restored {rows_restored} rows to {table_name}")

                except Exception as e:
                    logger.error(f"Restore table failed: {table_name}: {e}")
                    restore_stats["errors"].append(f"Table {table_name}: {str(e)}")
                    self.db.rollback()

            restore_stats["completed_at"] = datetime.utcnow().isoformat()
            logger.info(f"Restore completed: {restore_stats['total_rows_restored']} rows")

            return restore_stats

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise

    def list_backups(self, include_s3: bool = True) -> List[Dict[str, Any]]:
        """
        List all backups.

        Args:
            include_s3: Whether to include S3 backups

        Returns:
            List of backup metadata dicts
        """
        backups: List[Dict[str, Any]] = []

        # Local backups
        for meta_file in self.backup_dir.glob("*.meta"):
            try:
                with open(meta_file, "r") as f:
                    metadata = json.load(f)
                    metadata["storage_location"] = "local"
                    backups.append(metadata)
            except Exception as e:
                logger.warning(f"Could not read {meta_file}: {e}")

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
        seen_names = set()
        unique_backups: List[Dict[str, Any]] = []
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

    def delete_backup(self, backup_name: str, from_s3: bool = False) -> bool:
        """
        Delete a backup.

        Args:
            backup_name: Backup name
            from_s3: Whether to delete from S3

        Returns:
            True if deleted
        """
        if from_s3 and self.s3_manager:
            return self.s3_manager.delete_backup(backup_name)

        deleted = False
        for file_pattern in [f"{backup_name}*", f"*{backup_name}*"]:
            for backup_file in self.backup_dir.glob(file_pattern):
                try:
                    backup_file.unlink()
                    logger.info(f"Deleted: {backup_file}")
                    deleted = True
                except Exception as e:
                    logger.error(f"Delete failed: {backup_file}: {e}")

        return deleted

    def schedule_backup(self, cron_expression: str, **backup_kwargs: Any) -> str:
        """
        Schedule automatic backups.

        Args:
            cron_expression: Cron expression
            **backup_kwargs: create_backup arguments

        Returns:
            Schedule ID
        """
        # Placeholder for scheduler integration
        schedule_id = f"schedule_{datetime.utcnow().timestamp()}"
        logger.info(f"Scheduled: {schedule_id} with cron: {cron_expression}")
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
