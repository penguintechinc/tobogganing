"""S3 backup storage configuration and operations."""

import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

logger = logging.getLogger(__name__)


# Reserved S3 key segment for whole-DB backups; tenant IDs cannot start with "_".
GLOBAL_PREFIX_SEGMENT = "_global"
# Metadata scope values that mark a whole-DB (non-tenant) backup.
LEGACY_GLOBAL_SCOPES = frozenset({"whole_db", "global"})


@dataclass(slots=True)
class S3Config:
    """S3 configuration for backup storage."""

    enabled: bool
    endpoint_url: Optional[str]
    bucket: str
    region: str
    access_key: Optional[str]
    secret_key: Optional[str]
    prefix: str
    use_ssl: bool
    verify_ssl: bool

    @classmethod
    def from_env(cls) -> "S3Config":
        """Load S3 config from environment variables."""
        import os

        return cls(
            enabled=os.getenv("BACKUP_S3_ENABLED", "false").lower() == "true",
            endpoint_url=os.getenv("BACKUP_S3_ENDPOINT_URL"),
            bucket=os.getenv("BACKUP_S3_BUCKET", "sasewaddle-backups"),
            region=os.getenv("BACKUP_S3_REGION", "us-east-1"),
            access_key=os.getenv("BACKUP_S3_ACCESS_KEY"),
            secret_key=os.getenv("BACKUP_S3_SECRET_KEY"),
            prefix=os.getenv("BACKUP_S3_PREFIX", "backups/"),
            use_ssl=os.getenv("BACKUP_S3_USE_SSL", "true").lower() == "true",
            verify_ssl=os.getenv("BACKUP_S3_VERIFY_SSL", "true").lower() == "true",
        )


class S3Manager:
    """Manages S3 backup operations."""

    def __init__(self, config: S3Config) -> None:
        """
        Initialize S3 manager.

        Args:
            config: S3 configuration
        """
        self.config = config
        self.client: Any = None

        if self.config.enabled:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize boto3 S3 client."""
        if not S3_AVAILABLE:
            logger.error("S3 enabled but boto3 not installed")
            raise ImportError("boto3 required for S3 backups")

        try:
            session_config: Dict[str, str] = {}
            if self.config.access_key and self.config.secret_key:
                session_config["aws_access_key_id"] = self.config.access_key
                session_config["aws_secret_access_key"] = self.config.secret_key

            session = boto3.Session(**session_config)

            client_config: Dict[str, Any] = {
                "region_name": self.config.region,
                "use_ssl": self.config.use_ssl,
                "verify": self.config.verify_ssl,
            }

            if self.config.endpoint_url:
                client_config["endpoint_url"] = self.config.endpoint_url

            self.client = session.client("s3", **client_config)
            self._ensure_bucket()

            logger.info(f"S3 initialized: {self.config.bucket}")

        except NoCredentialsError:
            logger.error("S3 credentials not found")
            raise
        except Exception as e:
            logger.error(f"S3 init failed: {e}")
            raise

    def _ensure_bucket(self) -> None:
        """Ensure S3 bucket exists."""
        if not self.client:
            return

        try:
            self.client.head_bucket(Bucket=self.config.bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                self._create_bucket()
            else:
                logger.error(f"Bucket access error: {e}")
                raise

    def _create_bucket(self) -> None:
        """Create S3 bucket."""
        if not self.client:
            return

        try:
            if self.config.region == "us-east-1":
                self.client.create_bucket(Bucket=self.config.bucket)
            else:
                self.client.create_bucket(
                    Bucket=self.config.bucket,
                    CreateBucketConfiguration={"LocationConstraint": self.config.region},
                )
            logger.info(f"Bucket created: {self.config.bucket}")
        except ClientError as e:
            logger.error(f"Bucket creation failed: {e}")
            raise

    def tenant_base(self, tenant_id: Optional[str] = None) -> str:
        """Return the key prefix for a tenant (``{prefix}{tenant}/``) or whole-DB backups.

        Whole-DB backups live under the reserved ``{prefix}_global/`` prefix; tenant IDs
        may not start with ``_``, so no tenant prefix can ever alias it.
        """
        if not tenant_id:
            return f"{self.config.prefix}{GLOBAL_PREFIX_SEGMENT}/"
        if tenant_id.startswith("_"):
            raise ValueError("Tenant ID cannot start with '_' (reserved prefix)")
        return f"{self.config.prefix}{tenant_id}/"

    def key_belongs_to_tenant(self, s3_key: str, tenant_id: str) -> bool:
        """True if ``s3_key`` lies under ``tenant_id``'s prefix (no traversal)."""
        return ".." not in s3_key and s3_key.startswith(self.tenant_base(tenant_id))

    def upload_backup(
        self, backup_file: Path, backup_name: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload backup file to S3.

        Args:
            backup_file: Path to backup file
            backup_name: Backup name

        Returns:
            S3 metadata dict
        """
        if not self.client:
            raise RuntimeError("S3 client not initialized")

        try:
            s3_key = f"{self.tenant_base(tenant_id)}{backup_name}/{backup_file.name}"

            with open(backup_file, "rb") as f:
                self.client.upload_fileobj(
                    f,
                    self.config.bucket,
                    s3_key,
                    ExtraArgs={
                        "ContentType": "application/octet-stream",
                        "Metadata": {
                            "backup-name": backup_name,
                            "created-at": datetime.utcnow().isoformat(),
                        },
                    },
                )

            response = self.client.head_object(Bucket=self.config.bucket, Key=s3_key)

            return {
                "bucket": self.config.bucket,
                "s3_key": s3_key,
                "etag": response["ETag"].strip('"'),
                "size_bytes": response["ContentLength"],
                "uploaded_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise

    def upload_metadata(
        self, metadata_file: Path, backup_name: str, tenant_id: Optional[str] = None
    ) -> None:
        """Upload metadata file to S3."""
        if not self.client:
            return

        try:
            s3_key = f"{self.tenant_base(tenant_id)}{backup_name}/{metadata_file.name}"

            with open(metadata_file, "rb") as f:
                self.client.upload_fileobj(
                    f,
                    self.config.bucket,
                    s3_key,
                    ExtraArgs={"ContentType": "application/json"},
                )

            logger.debug(f"Metadata uploaded: {s3_key}")

        except Exception as e:
            logger.warning(f"Metadata upload failed: {e}")

    def download_backup(self, s3_key: str) -> Path:
        """
        Download backup from S3 to temp file.

        Args:
            s3_key: S3 object key

        Returns:
            Path to downloaded file
        """
        if not self.client:
            raise RuntimeError("S3 client not initialized")

        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".backup")
            temp_path = Path(temp_file.name)
            temp_file.close()

            self.client.download_file(self.config.bucket, s3_key, str(temp_path))

            logger.info(f"Downloaded from S3: {s3_key} -> {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise

    def list_backups(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List backups in S3; restricted to the tenant's prefix when tenant_id is set."""
        if not self.client:
            return []

        try:
            backups: List[Dict[str, Any]] = []
            base = self.tenant_base(tenant_id)
            paginator = self.client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=self.config.bucket, Prefix=base):
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]
                    if key.endswith("/") or key.endswith(".meta"):
                        continue

                    if tenant_id and not self.key_belongs_to_tenant(key, tenant_id):
                        continue
                    parts = key[len(base) :].split("/")
                    if len(parts) >= 2:
                        backup_name = parts[-2]
                        filename = parts[-1]

                        backups.append(
                            {
                                "backup_name": backup_name,
                                "filename": filename,
                                "s3_key": key,
                                "size_bytes": obj["Size"],
                                "last_modified": obj["LastModified"].isoformat(),
                                "storage_class": obj.get("StorageClass", "STANDARD"),
                            }
                        )

            return sorted(backups, key=lambda x: x["last_modified"], reverse=True)

        except Exception as e:
            logger.error(f"List S3 backups failed: {e}")
            return []

    def delete_backup(self, backup_name: str, tenant_id: Optional[str] = None) -> bool:
        """
        Delete backup from S3.

        Args:
            backup_name: Backup name

        Returns:
            True if deleted
        """
        if not self.client:
            return False

        try:
            prefix = f"{self.tenant_base(tenant_id)}{backup_name}/"
            response = self.client.list_objects_v2(Bucket=self.config.bucket, Prefix=prefix)

            if "Contents" not in response:
                return False

            objects_to_delete = [{"Key": obj["Key"]} for obj in response["Contents"]]

            if objects_to_delete:
                self.client.delete_objects(
                    Bucket=self.config.bucket, Delete={"Objects": objects_to_delete}
                )

                logger.info(f"Deleted {len(objects_to_delete)} S3 objects: {backup_name}")
                return True

            return False

        except Exception as e:
            logger.error(f"Delete S3 backup failed: {e}")
            return False

    def migrate_global_prefix(self, dry_run: bool = False) -> Dict[str, Any]:
        """Move legacy root-level whole-DB backups into the reserved ``_global/`` prefix.

        Only ``{prefix}{name}/{name}.meta`` folders whose metadata scope is whole-DB
        are moved; tenant folders never match. Each object is copied, verified by
        size/ETag, then the source deleted, so a re-run is a no-op (idempotent).
        """
        if not self.client:
            raise RuntimeError("S3 client not configured")
        prefix = self.config.prefix
        dest_base = self.tenant_base(None)
        report: Dict[str, Any] = {"examined": 0, "backups": [], "moved": 0, "skipped": 0}

        paginator = self.client.get_paginator("list_objects_v2")
        candidates: Dict[str, List[str]] = {}
        for page in paginator.paginate(Bucket=self.config.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(prefix) :]
                report["examined"] += 1
                parts = rel.split("/")
                if len(parts) != 2 or not parts[1] or parts[0].startswith("_"):
                    continue
                candidates.setdefault(parts[0], []).append(obj["Key"])

        for name, keys in sorted(candidates.items()):
            # Metadata is written as ``{backup_file}.with_suffix(".meta")``,
            # e.g. ``name.json.meta`` or ``name.json.gz.meta``.
            meta_keys = [
                k for k in keys if k.rsplit("/", 1)[1].startswith(name) and k.endswith(".meta")
            ]
            if len(meta_keys) != 1:
                report["skipped"] += 1
                continue
            meta_key = meta_keys[0]
            body = self.client.get_object(Bucket=self.config.bucket, Key=meta_key)["Body"].read()
            try:
                scope = json.loads(body.decode("utf-8")).get("scope", "")
            except (ValueError, UnicodeDecodeError):
                scope = ""
            if scope not in LEGACY_GLOBAL_SCOPES:
                report["skipped"] += 1
                continue
            report["backups"].append(name)
            for src in sorted(keys):
                dst = f"{dest_base}{src[len(prefix) :]}"
                if dry_run:
                    continue
                self.client.copy_object(
                    Bucket=self.config.bucket,
                    Key=dst,
                    CopySource={"Bucket": self.config.bucket, "Key": src},
                )
                s_head = self.client.head_object(Bucket=self.config.bucket, Key=src)
                d_head = self.client.head_object(Bucket=self.config.bucket, Key=dst)
                if (s_head["ContentLength"], s_head.get("ETag")) != (
                    d_head["ContentLength"],
                    d_head.get("ETag"),
                ):
                    raise RuntimeError(f"Copy verification failed for {src}; source kept")
                self.client.delete_object(Bucket=self.config.bucket, Key=src)
                report["moved"] += 1
        logger.info(f"migrate_global_prefix dry_run={dry_run} report={report}")
        return report

    def get_metadata(
        self, backup_name: str, tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata for S3 backup.

        Args:
            backup_name: Backup name

        Returns:
            Metadata dict or None
        """
        if not self.client:
            return None

        try:
            metadata_key = f"{self.tenant_base(tenant_id)}{backup_name}/{backup_name}.meta"
            obj = self.client.get_object(Bucket=self.config.bucket, Key=metadata_key)
            import json

            return json.loads(obj["Body"].read().decode("utf-8"))

        except ClientError:
            return None
        except Exception as e:
            logger.error(f"Get metadata failed: {e}")
            return None
