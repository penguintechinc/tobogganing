"""Database backup and restore functionality for SASEWaddle Manager."""

import os
import json
import gzip
import shutil
import hashlib
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
from urllib.parse import urlparse

from database import get_db, get_database_uri
from pydal import DAL

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

logger = logging.getLogger(__name__)

class S3Config:
    """S3 configuration for backup storage."""
    
    def __init__(self):
        self.enabled = os.getenv('BACKUP_S3_ENABLED', 'false').lower() == 'true'
        self.endpoint_url = os.getenv('BACKUP_S3_ENDPOINT_URL')  # For MINIO, etc.
        self.bucket = os.getenv('BACKUP_S3_BUCKET', 'sasewaddle-backups')
        self.region = os.getenv('BACKUP_S3_REGION', 'us-east-1')
        self.access_key = os.getenv('BACKUP_S3_ACCESS_KEY')
        self.secret_key = os.getenv('BACKUP_S3_SECRET_KEY')
        self.prefix = os.getenv('BACKUP_S3_PREFIX', 'backups/')
        # Optional: For custom S3-compatible providers
        self.use_ssl = os.getenv('BACKUP_S3_USE_SSL', 'true').lower() == 'true'
        self.verify_ssl = os.getenv('BACKUP_S3_VERIFY_SSL', 'true').lower() == 'true'


class BackupManager:
    """Manages database backup and restore operations with local and S3 support."""
    
    def __init__(self, backup_dir: str = "/backups"):
        """
        Initialize the backup manager.
        
        Args:
            backup_dir: Directory to store local backup files
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize S3 configuration
        self.s3_config = S3Config()
        self.s3_client = None
        
        if self.s3_config.enabled:
            self._init_s3_client()
    
    def _init_s3_client(self):
        """Initialize S3 client for backup storage."""
        if not S3_AVAILABLE:
            logger.error("S3 backup enabled but boto3 not installed")
            raise ImportError("boto3 required for S3 backups")
        
        try:
            # Build session configuration
            session_config = {}
            if self.s3_config.access_key and self.s3_config.secret_key:
                session_config['aws_access_key_id'] = self.s3_config.access_key
                session_config['aws_secret_access_key'] = self.s3_config.secret_key
            
            session = boto3.Session(**session_config)
            
            # Build client configuration
            client_config = {
                'region_name': self.s3_config.region,
                'use_ssl': self.s3_config.use_ssl,
                'verify': self.s3_config.verify_ssl
            }
            
            if self.s3_config.endpoint_url:
                client_config['endpoint_url'] = self.s3_config.endpoint_url
            
            self.s3_client = session.client('s3', **client_config)
            
            # Test connection and create bucket if needed
            self._ensure_s3_bucket()
            
            logger.info(f"S3 backup storage initialized: {self.s3_config.bucket}")
            
        except NoCredentialsError:
            logger.error("S3 credentials not found")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
    
    def _ensure_s3_bucket(self):
        """Ensure the S3 bucket exists."""
        try:
            self.s3_client.head_bucket(Bucket=self.s3_config.bucket)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                try:
                    if self.s3_config.region == 'us-east-1':
                        # us-east-1 doesn't need location constraint
                        self.s3_client.create_bucket(Bucket=self.s3_config.bucket)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.s3_config.bucket,
                            CreateBucketConfiguration={'LocationConstraint': self.s3_config.region}
                        )
                    logger.info(f"Created S3 bucket: {self.s3_config.bucket}")
                except ClientError as create_error:
                    logger.error(f"Failed to create S3 bucket: {create_error}")
                    raise
            else:
                logger.error(f"S3 bucket access error: {e}")
                raise
    
    def create_backup(
        self,
        backup_name: Optional[str] = None,
        compress: bool = True,
        encrypt: bool = False,
        encryption_key: Optional[str] = None,
        upload_to_s3: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Create a full database backup.
        
        Args:
            backup_name: Custom backup name (auto-generated if not provided)
            compress: Whether to compress the backup with gzip
            encrypt: Whether to encrypt the backup
            encryption_key: Encryption key (required if encrypt=True)
            upload_to_s3: Override S3 upload setting (defaults to S3 config)
            
        Returns:
            Backup metadata including file path and checksum
        """
        try:
            db = get_db()
            
            # Generate backup name if not provided
            if not backup_name:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_name = f"sasewaddle_backup_{timestamp}"
            
            # Determine file extension
            ext = ".json"
            if compress:
                ext += ".gz"
            if encrypt:
                ext += ".enc"
            
            backup_file = self.backup_dir / f"{backup_name}{ext}"
            
            # Export all tables
            backup_data = {
                "metadata": {
                    "version": "1.0",
                    "created_at": datetime.utcnow().isoformat(),
                    "db_uri": self._sanitize_db_uri(get_database_uri()),
                    "tables": []
                },
                "data": {}
            }
            
            # Backup each table
            for table_name in db.tables:
                table = db[table_name]
                rows = db(table).select()
                
                # Convert rows to JSON-serializable format
                table_data = []
                for row in rows:
                    row_dict = {}
                    for field in table.fields:
                        value = row[field]
                        # Handle datetime objects
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        row_dict[field] = value
                    table_data.append(row_dict)
                
                backup_data["data"][table_name] = table_data
                backup_data["metadata"]["tables"].append({
                    "name": table_name,
                    "row_count": len(table_data)
                })
            
            # Convert to JSON
            json_data = json.dumps(backup_data, indent=2)
            
            # Compress if requested
            if compress:
                json_bytes = json_data.encode('utf-8')
                with gzip.open(backup_file, 'wb') as f:
                    f.write(json_bytes)
            else:
                with open(backup_file, 'w') as f:
                    f.write(json_data)
            
            # Encrypt if requested
            if encrypt:
                if not encryption_key:
                    raise ValueError("Encryption key required for encrypted backups")
                self._encrypt_file(backup_file, encryption_key)
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_file)
            
            # Upload to S3 if enabled
            s3_info = None
            should_upload_s3 = upload_to_s3 if upload_to_s3 is not None else self.s3_config.enabled
            
            if should_upload_s3 and self.s3_client:
                s3_info = self._upload_backup_to_s3(backup_file, backup_name)
            
            # Create metadata
            metadata = {
                "backup_name": backup_name,
                "file_path": str(backup_file),
                "created_at": datetime.utcnow().isoformat(),
                "compressed": compress,
                "encrypted": encrypt,
                "checksum": checksum,
                "size_bytes": backup_file.stat().st_size,
                "table_count": len(backup_data["metadata"]["tables"]),
                "total_rows": sum(t["row_count"] for t in backup_data["metadata"]["tables"]),
                "s3_info": s3_info
            }
            
            metadata_file = backup_file.with_suffix('.meta')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Also upload metadata to S3 if backup was uploaded
            if s3_info:
                self._upload_metadata_to_s3(metadata_file, backup_name)
            
            logger.info(f"Backup created successfully: {backup_file}")
            if s3_info:
                logger.info(f"Backup uploaded to S3: {s3_info['s3_key']}")
            
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
        from_s3: bool = False
    ) -> Dict[str, Any]:
        """
        Restore database from a backup file.
        
        Args:
            backup_path: Path to the backup file or S3 key
            decrypt: Whether the backup is encrypted
            decryption_key: Decryption key (required if decrypt=True)
            verify_checksum: Whether to verify backup integrity
            from_s3: Whether to download from S3 first
            
        Returns:
            Restore statistics
        """
        try:
            # Handle S3 download if needed
            if from_s3 and self.s3_client:
                backup_file = self._download_backup_from_s3(backup_path)
            else:
                backup_file = Path(backup_path)
                
                if not backup_file.exists():
                    raise FileNotFoundError(f"Backup file not found: {backup_file}")
            
            # Load metadata if available
            metadata_file = backup_file.with_suffix('.meta')
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                # Verify checksum if requested
                if verify_checksum and 'checksum' in metadata:
                    actual_checksum = self._calculate_checksum(backup_file)
                    if actual_checksum != metadata['checksum']:
                        raise ValueError("Backup file checksum verification failed")
            
            # Decrypt if needed
            if decrypt:
                if not decryption_key:
                    raise ValueError("Decryption key required for encrypted backups")
                backup_file = self._decrypt_file(backup_file, decryption_key)
            
            # Decompress and load data
            if backup_file.suffix == '.gz':
                with gzip.open(backup_file, 'rb') as f:
                    json_data = f.read().decode('utf-8')
            else:
                with open(backup_file, 'r') as f:
                    json_data = f.read()
            
            backup_data = json.loads(json_data)
            
            # Validate backup format
            if 'metadata' not in backup_data or 'data' not in backup_data:
                raise ValueError("Invalid backup file format")
            
            db = get_db()
            
            # Begin restore
            restore_stats = {
                "started_at": datetime.utcnow().isoformat(),
                "tables_restored": [],
                "total_rows_restored": 0,
                "errors": []
            }
            
            # Restore each table
            for table_name, table_data in backup_data['data'].items():
                try:
                    if table_name not in db.tables:
                        logger.warning(f"Table {table_name} not found in current schema, skipping")
                        restore_stats["errors"].append(f"Table {table_name} not found")
                        continue
                    
                    table = db[table_name]
                    
                    # Clear existing data (optional - could make this configurable)
                    db(table).delete()
                    
                    # Insert backup data
                    rows_restored = 0
                    for row_data in table_data:
                        # Convert datetime strings back to datetime objects
                        for field, value in row_data.items():
                            if field in table.fields:
                                field_type = table[field].type
                                if field_type == 'datetime' and value:
                                    row_data[field] = datetime.fromisoformat(value)
                        
                        table.insert(**row_data)
                        rows_restored += 1
                    
                    db.commit()
                    
                    restore_stats["tables_restored"].append({
                        "name": table_name,
                        "rows": rows_restored
                    })
                    restore_stats["total_rows_restored"] += rows_restored
                    
                    logger.info(f"Restored {rows_restored} rows to table {table_name}")
                    
                except Exception as e:
                    logger.error(f"Error restoring table {table_name}: {e}")
                    restore_stats["errors"].append(f"Table {table_name}: {str(e)}")
                    db.rollback()
            
            restore_stats["completed_at"] = datetime.utcnow().isoformat()
            logger.info(f"Restore completed: {restore_stats['total_rows_restored']} rows restored")
            
            return restore_stats
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise
    
    def list_backups(self, include_s3: bool = True) -> List[Dict[str, Any]]:
        """
        List all available backups from local storage and optionally S3.
        
        Args:
            include_s3: Whether to include S3 backups in the list
        
        Returns:
            List of backup metadata
        """
        backups = []
        
        # Find local backups
        for meta_file in self.backup_dir.glob("*.meta"):
            try:
                with open(meta_file, 'r') as f:
                    metadata = json.load(f)
                    metadata['storage_location'] = 'local'
                    backups.append(metadata)
            except Exception as e:
                logger.warning(f"Could not read metadata file {meta_file}: {e}")
        
        # Add S3 backups if enabled and requested
        if include_s3 and self.s3_client:
            s3_backups = self.list_s3_backups()
            for s3_backup in s3_backups:
                s3_backup['storage_location'] = 's3'
                # Try to find corresponding metadata
                try:
                    metadata_key = f"{self.s3_config.prefix}{s3_backup['backup_name']}/{s3_backup['backup_name']}.meta"
                    metadata_obj = self.s3_client.get_object(Bucket=self.s3_config.bucket, Key=metadata_key)
                    metadata = json.loads(metadata_obj['Body'].read().decode('utf-8'))
                    metadata.update(s3_backup)
                    backups.append(metadata)
                except ClientError:
                    # No metadata file, use basic info
                    s3_backup.update({
                        'created_at': s3_backup['last_modified'],
                        'compressed': s3_backup['filename'].endswith('.gz'),
                        'encrypted': s3_backup['filename'].endswith('.enc')
                    })
                    backups.append(s3_backup)
        
        # Remove duplicates (prefer S3 version if both exist)
        seen_names = set()
        unique_backups = []
        for backup in sorted(backups, key=lambda x: (x.get('created_at', ''), x.get('storage_location') == 's3'), reverse=True):
            name = backup.get('backup_name')
            if name not in seen_names:
                seen_names.add(name)
                unique_backups.append(backup)
        
        return unique_backups
    
    def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a backup and its metadata.
        
        Args:
            backup_name: Name of the backup to delete
            
        Returns:
            True if deleted successfully
        """
        deleted = False
        
        # Find and delete backup files
        for file_pattern in [f"{backup_name}*", f"*{backup_name}*"]:
            for backup_file in self.backup_dir.glob(file_pattern):
                try:
                    backup_file.unlink()
                    logger.info(f"Deleted backup file: {backup_file}")
                    deleted = True
                except Exception as e:
                    logger.error(f"Error deleting {backup_file}: {e}")
        
        return deleted
    
    def schedule_backup(self, cron_expression: str, **backup_kwargs) -> str:
        """
        Schedule automatic backups using cron expression.
        
        Args:
            cron_expression: Cron expression for scheduling
            **backup_kwargs: Arguments to pass to create_backup
            
        Returns:
            Schedule ID
        """
        # This would integrate with a scheduler like APScheduler
        # For now, return a placeholder
        return f"schedule_{datetime.utcnow().timestamp()}"
    
    def _sanitize_db_uri(self, uri: str) -> str:
        """Remove sensitive information from database URI."""
        # Remove password from URI
        import re
        return re.sub(r'://[^:]+:[^@]+@', '://***:***@', uri)
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _encrypt_file(self, file_path: Path, key: str) -> Path:
        """
        Encrypt a file using AES encryption.
        
        Note: This is a placeholder. In production, use proper encryption
        library like cryptography.fernet
        """
        # Placeholder for encryption logic
        logger.warning("Encryption not yet implemented - file not encrypted")
        return file_path
    
    def _decrypt_file(self, file_path: Path, key: str) -> Path:
        """
        Decrypt a file.
        
        Note: This is a placeholder. In production, use proper decryption
        library like cryptography.fernet
        """
        # Placeholder for decryption logic
        logger.warning("Decryption not yet implemented - assuming file not encrypted")
        return file_path
    
    def _upload_backup_to_s3(self, backup_file: Path, backup_name: str) -> Dict[str, Any]:
        """Upload backup file to S3."""
        try:
            s3_key = f"{self.s3_config.prefix}{backup_name}/{backup_file.name}"
            
            # Upload the backup file
            with open(backup_file, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f, 
                    self.s3_config.bucket, 
                    s3_key,
                    ExtraArgs={
                        'ContentType': 'application/octet-stream',
                        'Metadata': {
                            'backup-name': backup_name,
                            'created-at': datetime.utcnow().isoformat()
                        }
                    }
                )
            
            # Get object info
            response = self.s3_client.head_object(Bucket=self.s3_config.bucket, Key=s3_key)
            
            return {
                'bucket': self.s3_config.bucket,
                's3_key': s3_key,
                'etag': response['ETag'].strip('"'),
                'size_bytes': response['ContentLength'],
                'uploaded_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to upload backup to S3: {e}")
            raise
    
    def _upload_metadata_to_s3(self, metadata_file: Path, backup_name: str):
        """Upload metadata file to S3."""
        try:
            s3_key = f"{self.s3_config.prefix}{backup_name}/{metadata_file.name}"
            
            with open(metadata_file, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.s3_config.bucket,
                    s3_key,
                    ExtraArgs={'ContentType': 'application/json'}
                )
            
            logger.debug(f"Uploaded metadata to S3: {s3_key}")
            
        except Exception as e:
            logger.warning(f"Failed to upload metadata to S3: {e}")
    
    def _download_backup_from_s3(self, s3_key: str) -> Path:
        """Download backup file from S3 to temporary local storage."""
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.backup')
            temp_path = Path(temp_file.name)
            temp_file.close()
            
            # Download from S3
            self.s3_client.download_file(
                self.s3_config.bucket,
                s3_key,
                str(temp_path)
            )
            
            logger.info(f"Downloaded backup from S3: {s3_key} -> {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to download backup from S3: {e}")
            raise
    
    def list_s3_backups(self) -> List[Dict[str, Any]]:
        """List all backups stored in S3."""
        if not self.s3_client:
            return []
        
        try:
            backups = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.s3_config.bucket, Prefix=self.s3_config.prefix):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    key = obj['Key']
                    # Skip metadata files and directories
                    if key.endswith('/') or key.endswith('.meta'):
                        continue
                    
                    # Parse backup info from key
                    parts = key.replace(self.s3_config.prefix, '').split('/')
                    if len(parts) >= 2:
                        backup_name = parts[0]
                        filename = parts[-1]
                        
                        backups.append({
                            'backup_name': backup_name,
                            'filename': filename,
                            's3_key': key,
                            'size_bytes': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'storage_class': obj.get('StorageClass', 'STANDARD')
                        })
            
            return sorted(backups, key=lambda x: x['last_modified'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to list S3 backups: {e}")
            return []
    
    def delete_s3_backup(self, backup_name: str) -> bool:
        """Delete a backup from S3."""
        if not self.s3_client:
            return False
        
        try:
            # List all objects for this backup
            prefix = f"{self.s3_config.prefix}{backup_name}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_config.bucket,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return False
            
            # Delete all objects
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            
            if objects_to_delete:
                self.s3_client.delete_objects(
                    Bucket=self.s3_config.bucket,
                    Delete={'Objects': objects_to_delete}
                )
                
                logger.info(f"Deleted {len(objects_to_delete)} S3 objects for backup: {backup_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete S3 backup: {e}")
            return False


# CLI interface for backup operations
def backup_cli():
    """Command-line interface for backup operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SASEWaddle Database Backup Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create backup command
    backup_parser = subparsers.add_parser('create', help='Create a backup')
    backup_parser.add_argument('--name', help='Backup name')
    backup_parser.add_argument('--compress', action='store_true', help='Compress backup')
    backup_parser.add_argument('--encrypt', action='store_true', help='Encrypt backup')
    backup_parser.add_argument('--s3', action='store_true', help='Upload to S3')
    
    # Restore backup command
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('path', help='Path to backup file or S3 key')
    restore_parser.add_argument('--decrypt', action='store_true', help='Decrypt backup')
    restore_parser.add_argument('--from-s3', action='store_true', help='Restore from S3')
    
    # List backups command
    list_parser = subparsers.add_parser('list', help='List available backups')
    list_parser.add_argument('--local-only', action='store_true', help='List only local backups')
    list_parser.add_argument('--s3-only', action='store_true', help='List only S3 backups')
    
    # Delete backup command
    delete_parser = subparsers.add_parser('delete', help='Delete a backup')
    delete_parser.add_argument('name', help='Backup name to delete')
    delete_parser.add_argument('--from-s3', action='store_true', help='Delete from S3')
    
    # S3 status command
    s3_parser = subparsers.add_parser('s3-status', help='Check S3 configuration')
    
    args = parser.parse_args()
    
    manager = BackupManager()
    
    if args.command == 'create':
        result = manager.create_backup(
            backup_name=args.name,
            compress=args.compress,
            encrypt=args.encrypt,
            upload_to_s3=args.s3
        )
        print(f"Backup created: {result['file_path']}")
        if result.get('s3_info'):
            print(f"Uploaded to S3: {result['s3_info']['s3_key']}")
        
    elif args.command == 'restore':
        result = manager.restore_backup(
            backup_path=args.path,
            decrypt=args.decrypt,
            from_s3=args.from_s3
        )
        print(f"Restore completed: {result['total_rows_restored']} rows restored")
        
    elif args.command == 'list':
        if args.s3_only:
            backups = manager.list_s3_backups()
        elif args.local_only:
            backups = manager.list_backups(include_s3=False)
        else:
            backups = manager.list_backups(include_s3=True)
            
        for backup in backups:
            location = backup.get('storage_location', 'unknown')
            print(f"- {backup.get('backup_name', 'unknown')} ({backup.get('created_at', 'unknown')}) [{location}]")
            
    elif args.command == 'delete':
        if args.from_s3:
            if manager.delete_s3_backup(args.name):
                print(f"S3 backup {args.name} deleted")
            else:
                print(f"S3 backup {args.name} not found")
        else:
            if manager.delete_backup(args.name):
                print(f"Backup {args.name} deleted")
            else:
                print(f"Backup {args.name} not found")
                
    elif args.command == 's3-status':
        config = manager.s3_config
        print(f"S3 Enabled: {config.enabled}")
        if config.enabled:
            print(f"Bucket: {config.bucket}")
            print(f"Region: {config.region}")
            print(f"Endpoint: {config.endpoint_url or 'Default AWS'}")
            print(f"Connected: {manager.s3_client is not None}")
            
            if manager.s3_client:
                try:
                    manager.s3_client.head_bucket(Bucket=config.bucket)
                    print("Connection Test: ✓ Success")
                except Exception as e:
                    print(f"Connection Test: ✗ Failed ({e})")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    backup_cli()