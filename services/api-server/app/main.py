"""Flask application entry point"""

import os
import logging
from threading import Thread
from flask import Flask, jsonify
from flask_security import Security, SQLAlchemyUserDatastore, hash_password
from pydal import DAL, Field

from .config import AppConfig
from .api import create_api_blueprint
from .grpc.server import start_grpc_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(config: AppConfig | None = None) -> Flask:
    """Application factory

    Args:
        config: Application configuration (loaded from env if not provided)

    Returns:
        Configured Flask application
    """
    if config is None:
        config = AppConfig.from_env()

    app = Flask(__name__)

    # Flask configuration
    app.config['SECRET_KEY'] = config.jwt.secret_key
    app.config['SECURITY_PASSWORD_SALT'] = config.jwt.security_password_salt
    app.config['SECURITY_TOKEN_AUTHENTICATION_HEADER'] = 'Authorization'
    app.config['SECURITY_TOKEN_AUTHENTICATION_SCHEME'] = 'Bearer'
    app.config['WTF_CSRF_ENABLED'] = False

    # Initialize database
    db_uri = (
        f"{config.database.db_type}://"
        f"{config.database.db_user}:{config.database.db_password}@"
        f"{config.database.db_host}:{config.database.db_port}/"
        f"{config.database.db_name}"
    )

    db = DAL(
        db_uri,
        pool_size=config.database.db_pool_size,
        migrate_enabled=True,
    )

    # Define database tables
    _define_tables(db)

    # Setup Flask-Security-Too
    user_datastore = SQLAlchemyUserDatastore(None, None)
    security = Security(app, user_datastore)

    # Store config and db in app context
    app.config['db'] = db
    app.config['config'] = config

    # Register blueprints
    api_bp = create_api_blueprint(db)
    app.register_blueprint(api_bp)

    # Health check endpoints
    @app.route('/health')
    def health() -> tuple[dict, int]:
        """Health check endpoint"""
        return {'status': 'healthy', 'service': 'api-server'}, 200

    @app.route('/healthz')
    def healthz() -> tuple[dict, int]:
        """Kubernetes health check"""
        return {'status': 'ok'}, 200

    # Error handlers
    @app.errorhandler(400)
    def bad_request(error) -> tuple[dict, int]:
        """Bad request handler"""
        return {'error': 'Bad request', 'message': str(error)}, 400

    @app.errorhandler(401)
    def unauthorized(error) -> tuple[dict, int]:
        """Unauthorized handler"""
        return {'error': 'Unauthorized', 'message': str(error)}, 401

    @app.errorhandler(403)
    def forbidden(error) -> tuple[dict, int]:
        """Forbidden handler"""
        return {'error': 'Forbidden', 'message': str(error)}, 403

    @app.errorhandler(404)
    def not_found(error) -> tuple[dict, int]:
        """Not found handler"""
        return {'error': 'Not found', 'message': str(error)}, 404

    @app.errorhandler(500)
    def internal_error(error) -> tuple[dict, int]:
        """Internal server error handler"""
        logger.error(f"Internal error: {error}")
        return {'error': 'Internal server error'}, 500

    # Start gRPC server in background thread
    grpc_thread = Thread(
        target=start_grpc_server,
        args=(config.grpc.grpc_host, config.grpc.grpc_port, db),
        daemon=True,
    )
    grpc_thread.start()
    logger.info(f"gRPC server starting on {config.grpc.grpc_host}:{config.grpc.grpc_port}")

    return app


def _define_tables(db: DAL) -> None:
    """Define PyDAL database tables

    Args:
        db: PyDAL database instance
    """
    # Users table
    db.define_table(
        'users',
        Field('email', 'string', unique=True, requires='IS_EMAIL()'),
        Field('username', 'string', unique=True),
        Field('password', 'string'),
        Field('active', 'boolean', default=True),
        Field('fs_uniquifier', 'string', unique=True),
        Field('created_at', 'datetime', default='now()'),
        migrate=True,
    )

    # Clients table
    db.define_table(
        'clients',
        Field('client_id', 'string', unique=True),
        Field('client_type', 'string'),  # USER, HYPERVISOR_LXD, etc.
        Field('hostname', 'string'),
        Field('ip_address', 'string'),
        Field('initial_secret', 'string'),
        Field('auth_token', 'string'),
        Field('public_key', 'string'),
        Field('active', 'boolean', default=True),
        Field('version', 'string'),
        Field('last_seen', 'datetime'),
        Field('created_at', 'datetime', default='now()'),
        migrate=True,
    )

    # Roles table
    db.define_table(
        'roles',
        Field('name', 'string', unique=True),
        Field('description', 'text'),
        migrate=True,
    )

    # User-Role mapping table
    db.define_table(
        'user_roles',
        Field('user_id', 'reference users'),
        Field('role_id', 'reference roles'),
        migrate=True,
    )

    # Policies table
    db.define_table(
        'policies',
        Field('policy_id', 'string', unique=True),
        Field('name', 'string'),
        Field('namespace', 'string'),
        Field('priority', 'integer'),
        Field('action', 'string'),  # ALLOW, DENY
        Field('direction', 'string'),  # INGRESS, EGRESS, BIDIRECTIONAL
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default='now()'),
        Field('updated_at', 'datetime', default='now()'),
        Field('created_by', 'string'),
        migrate=True,
    )


def run() -> None:
    """Run the Flask application"""
    config = AppConfig.from_env()
    app = create_app(config)
    app.run(
        host=config.api_host,
        port=config.api_port,
        debug=config.flask_debug,
    )


if __name__ == '__main__':
    run()
