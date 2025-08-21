"""Backup and restore API routes for SASEWaddle Manager."""

import os
from datetime import datetime
from py4web import action, request, response, abort, redirect, URL
from py4web.core import Fixture
import json

from backup import BackupManager
from web.auth import get_current_user, user_manager

# Initialize backup manager
backup_manager = BackupManager(
    backup_dir=os.getenv('BACKUP_DIR', '/data/backups')
)

@action('api/backup/create', method=['POST'])
@action.uses('json')
async def create_backup():
    """Create a database backup."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        # Get backup options from request
        data = await request.json()
        
        backup_name = data.get('name')
        compress = data.get('compress', True)
        encrypt = data.get('encrypt', False)
        encryption_key = data.get('encryption_key')
        upload_to_s3 = data.get('upload_to_s3')
        
        # Create backup
        result = backup_manager.create_backup(
            backup_name=backup_name,
            compress=compress,
            encrypt=encrypt,
            encryption_key=encryption_key,
            upload_to_s3=upload_to_s3
        )
        
        # Log the backup operation
        import structlog
        logger = structlog.get_logger()
        logger.info("Backup created",
                   user_id=user['id'],
                   backup_name=result['backup_name'],
                   size_bytes=result['size_bytes'])
        
        return {
            "success": True,
            "backup": result
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/restore', method=['POST'])
@action.uses('json')
async def restore_backup():
    """Restore database from backup."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        # Get restore options from request
        data = await request.json()
        
        backup_path = data.get('backup_path')
        if not backup_path:
            response.status = 400
            return {"error": "backup_path is required"}
        
        decrypt = data.get('decrypt', False)
        decryption_key = data.get('decryption_key')
        verify_checksum = data.get('verify_checksum', True)
        from_s3 = data.get('from_s3', False)
        
        # Perform restore
        result = backup_manager.restore_backup(
            backup_path=backup_path,
            decrypt=decrypt,
            decryption_key=decryption_key,
            verify_checksum=verify_checksum,
            from_s3=from_s3
        )
        
        # Log the restore operation
        import structlog
        logger = structlog.get_logger()
        logger.warning("Database restored from backup",
                      user_id=user['id'],
                      backup_path=backup_path,
                      rows_restored=result['total_rows_restored'])
        
        return {
            "success": True,
            "restore_stats": result
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/list', method=['GET'])
@action.uses('json')
async def list_backups():
    """List available backups."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        backups = backup_manager.list_backups()
        
        # Filter based on user permissions
        if not user_manager.has_permission(user, 'admin'):
            # Non-admins can only see backup metadata, not paths
            backups = [
                {
                    'backup_name': b['backup_name'],
                    'created_at': b['created_at'],
                    'size_bytes': b.get('size_bytes', 0),
                    'compressed': b.get('compressed', False),
                    'encrypted': b.get('encrypted', False)
                }
                for b in backups
            ]
        
        return {
            "success": True,
            "backups": backups,
            "count": len(backups)
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/delete/<backup_name>', method=['DELETE'])
@action.uses('json')
async def delete_backup(backup_name):
    """Delete a backup."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        deleted = backup_manager.delete_backup(backup_name)
        
        if deleted:
            # Log the deletion
            import structlog
            logger = structlog.get_logger()
            logger.warning("Backup deleted",
                          user_id=user['id'],
                          backup_name=backup_name)
            
            return {
                "success": True,
                "message": f"Backup {backup_name} deleted"
            }
        else:
            response.status = 404
            return {"error": f"Backup {backup_name} not found"}
            
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/schedule', method=['POST'])
@action.uses('json')
async def schedule_backup():
    """Schedule automatic backups."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        data = await request.json()
        
        cron_expression = data.get('cron_expression')
        if not cron_expression:
            response.status = 400
            return {"error": "cron_expression is required"}
        
        # Get backup options
        backup_options = {
            'compress': data.get('compress', True),
            'encrypt': data.get('encrypt', False),
            'encryption_key': data.get('encryption_key')
        }
        
        # Schedule the backup
        schedule_id = backup_manager.schedule_backup(
            cron_expression=cron_expression,
            **backup_options
        )
        
        # Log the scheduling
        import structlog
        logger = structlog.get_logger()
        logger.info("Backup scheduled",
                   user_id=user['id'],
                   schedule_id=schedule_id,
                   cron_expression=cron_expression)
        
        return {
            "success": True,
            "schedule_id": schedule_id,
            "cron_expression": cron_expression
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/download/<backup_name>', method=['GET'])
async def download_backup(backup_name):
    """Download a backup file."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        # Find the backup file
        backups = backup_manager.list_backups()
        backup = next((b for b in backups if b['backup_name'] == backup_name), None)
        
        if not backup:
            response.status = 404
            return {"error": f"Backup {backup_name} not found"}
        
        file_path = backup['file_path']
        
        if not os.path.exists(file_path):
            response.status = 404
            return {"error": "Backup file not found on disk"}
        
        # Set headers for file download
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        
        # Stream the file
        with open(file_path, 'rb') as f:
            return f.read()
            
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/upload', method=['POST'])
async def upload_backup():
    """Upload a backup file for restoration."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        # Get uploaded file
        files = await request.files()
        if 'backup' not in files:
            response.status = 400
            return {"error": "No backup file uploaded"}
        
        backup_file = files['backup']
        
        # Save to backup directory
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix='sasewaddle_upload_')
        file_path = os.path.join(temp_dir, backup_file.filename)
        
        with open(file_path, 'wb') as f:
            f.write(backup_file.file.read())
        
        # Validate backup file
        with open(file_path, 'rb') as f:
            # Check if it's a valid backup (basic validation)
            content = f.read(100)
            is_gzip = content.startswith(b'\x1f\x8b')  # gzip magic number
            is_json = content.startswith(b'{')
            
            if not (is_gzip or is_json):
                os.remove(file_path)
                response.status = 400
                return {"error": "Invalid backup file format"}
        
        # Move to backup directory
        import shutil
        backup_dir = os.getenv('BACKUP_DIR', '/data/backups')
        final_path = os.path.join(backup_dir, backup_file.filename)
        shutil.move(file_path, final_path)
        
        # Log the upload
        import structlog
        logger = structlog.get_logger()
        logger.info("Backup uploaded",
                   user_id=user['id'],
                   filename=backup_file.filename,
                   size_bytes=os.path.getsize(final_path))
        
        return {
            "success": True,
            "message": "Backup uploaded successfully",
            "file_path": final_path,
            "filename": backup_file.filename
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/s3/status', method=['GET'])
@action.uses('json')
async def s3_backup_status():
    """Get S3 backup configuration status."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        s3_config = backup_manager.s3_config
        
        status = {
            "s3_enabled": s3_config.enabled,
            "bucket": s3_config.bucket if s3_config.enabled else None,
            "region": s3_config.region if s3_config.enabled else None,
            "endpoint_url": s3_config.endpoint_url if s3_config.enabled else None,
            "prefix": s3_config.prefix if s3_config.enabled else None,
            "connected": backup_manager.s3_client is not None
        }
        
        # Test connection if enabled
        if s3_config.enabled and backup_manager.s3_client:
            try:
                backup_manager.s3_client.head_bucket(Bucket=s3_config.bucket)
                status["connection_test"] = "success"
            except Exception as e:
                status["connection_test"] = f"failed: {str(e)}"
        
        return {
            "success": True,
            "s3_status": status
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/s3/list', method=['GET'])
@action.uses('json')
async def list_s3_backups():
    """List backups stored in S3."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        if not backup_manager.s3_config.enabled:
            return {
                "success": True,
                "backups": [],
                "message": "S3 backup storage is disabled"
            }
        
        s3_backups = backup_manager.list_s3_backups()
        
        return {
            "success": True,
            "backups": s3_backups,
            "count": len(s3_backups)
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}

@action('api/backup/s3/delete/<backup_name>', method=['DELETE'])
@action.uses('json')
async def delete_s3_backup(backup_name):
    """Delete a backup from S3."""
    # Check authentication and permissions
    user = get_current_user()
    if not user or not user_manager.has_permission(user, 'admin'):
        response.status = 403
        return {"error": "Admin permission required"}
    
    try:
        if not backup_manager.s3_config.enabled:
            response.status = 400
            return {"error": "S3 backup storage is disabled"}
        
        deleted = backup_manager.delete_s3_backup(backup_name)
        
        if deleted:
            # Log the deletion
            import structlog
            logger = structlog.get_logger()
            logger.warning("S3 backup deleted",
                          user_id=user['id'],
                          backup_name=backup_name)
            
            return {
                "success": True,
                "message": f"S3 backup {backup_name} deleted"
            }
        else:
            response.status = 404
            return {"error": f"S3 backup {backup_name} not found"}
            
    except Exception as e:
        response.status = 500
        return {"error": str(e)}