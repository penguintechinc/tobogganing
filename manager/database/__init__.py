"""Database initialization and configuration for SASEWaddle Manager."""

import os
from datetime import datetime
from typing import Optional, List
from pydal import DAL, Field
from pydal.validators import *
import logging

logger = logging.getLogger(__name__)

# Global database instances
db: Optional[DAL] = None
db_read: Optional[DAL] = None

def get_database_uri() -> str:
    """Get primary database URI from environment variables."""
    db_type = os.getenv('DB_TYPE', 'mysql')
    
    if db_type == 'mysql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '3306')
        user = os.getenv('DB_USER', 'sasewaddle')
        password = os.getenv('DB_PASSWORD', 'sasewaddle')
        database = os.getenv('DB_NAME', 'sasewaddle')
        
        # Build URI with optional TLS parameters
        uri = f"mysql://{user}:{password}@{host}:{port}/{database}"
        
        # Add TLS parameters if configured
        tls_params = []
        if os.getenv('DB_TLS_ENABLED', 'false').lower() == 'true':
            tls_params.append('ssl=true')
            
            # SSL certificate files (optional)
            if ssl_ca := os.getenv('DB_TLS_CA_CERT'):
                tls_params.append(f'ssl-ca={ssl_ca}')
            if ssl_cert := os.getenv('DB_TLS_CLIENT_CERT'):
                tls_params.append(f'ssl-cert={ssl_cert}')
            if ssl_key := os.getenv('DB_TLS_CLIENT_KEY'):
                tls_params.append(f'ssl-key={ssl_key}')
            
            # SSL verification mode
            ssl_verify = os.getenv('DB_TLS_VERIFY_MODE', 'VERIFY_CA')
            if ssl_verify in ['VERIFY_IDENTITY', 'VERIFY_CA', 'DISABLED']:
                tls_params.append(f'ssl-mode={ssl_verify}')
        
        # Add connection parameters
        conn_params = []
        if charset := os.getenv('DB_CHARSET', 'utf8mb4'):
            conn_params.append(f'charset={charset}')
        if collation := os.getenv('DB_COLLATION'):
            conn_params.append(f'collation={collation}')
        if timeout := os.getenv('DB_CONNECT_TIMEOUT'):
            conn_params.append(f'connect_timeout={timeout}')
        
        # Combine all parameters
        all_params = tls_params + conn_params
        if all_params:
            uri += '?' + '&'.join(all_params)
        
        return uri
    
    elif db_type == 'postgresql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        user = os.getenv('DB_USER', 'sasewaddle')
        password = os.getenv('DB_PASSWORD', 'sasewaddle')
        database = os.getenv('DB_NAME', 'sasewaddle')
        
        # Build URI with optional TLS parameters
        uri = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        
        # Add TLS parameters if configured
        tls_params = []
        if os.getenv('DB_TLS_ENABLED', 'false').lower() == 'true':
            ssl_mode = os.getenv('DB_TLS_VERIFY_MODE', 'require')
            tls_params.append(f'sslmode={ssl_mode}')
            
            # SSL certificate files (optional)
            if ssl_ca := os.getenv('DB_TLS_CA_CERT'):
                tls_params.append(f'sslrootcert={ssl_ca}')
            if ssl_cert := os.getenv('DB_TLS_CLIENT_CERT'):
                tls_params.append(f'sslcert={ssl_cert}')
            if ssl_key := os.getenv('DB_TLS_CLIENT_KEY'):
                tls_params.append(f'sslkey={ssl_key}')
        
        # Add connection parameters
        conn_params = []
        if timeout := os.getenv('DB_CONNECT_TIMEOUT'):
            conn_params.append(f'connect_timeout={timeout}')
        
        # Combine all parameters
        all_params = tls_params + conn_params
        if all_params:
            uri += '?' + '&'.join(all_params)
        
        return uri
    
    elif db_type == 'sqlite':
        db_path = os.getenv('DB_PATH', '/data/sasewaddle.db')
        return f"sqlite://{db_path}"
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

def get_read_replica_uri() -> Optional[str]:
    """Get read replica database URI if configured."""
    if not os.getenv('DB_READ_REPLICA_ENABLED', 'false').lower() == 'true':
        return None
    
    db_type = os.getenv('DB_TYPE', 'mysql')
    
    if db_type == 'mysql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '3306'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'sasewaddle'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'sasewaddle'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'sasewaddle'))
        
        return f"mysql://{user}:{password}@{host}:{port}/{database}"
    
    elif db_type == 'postgresql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '5432'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'sasewaddle'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'sasewaddle'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'sasewaddle'))
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    # SQLite doesn't support read replicas
    return None

def initialize_database() -> None:
    """Initialize the database connections and schema."""
    global db, db_read
    
    try:
        # Initialize primary database
        primary_uri = get_database_uri()
        logger.info(f"Connecting to primary database: {primary_uri.split('@')[0]}@***")
        
        db = DAL(
            primary_uri,
            pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
            migrate=True,
            fake_migrate=False,
            check_reserved=['mysql', 'postgresql'],
            lazy_tables=True
        )
        
        # Initialize read replica if configured
        read_replica_uri = get_read_replica_uri()
        if read_replica_uri:
            logger.info(f"Connecting to read replica: {read_replica_uri.split('@')[0]}@***")
            db_read = DAL(
                read_replica_uri,
                pool_size=int(os.getenv('DB_READ_POOL_SIZE', '5')),
                migrate=False,  # Don't migrate on read replicas
                fake_migrate=False,
                check_reserved=['mysql', 'postgresql'],
                lazy_tables=True
            )
        else:
            # Use primary database for reads if no replica configured
            db_read = db
            logger.info("No read replica configured, using primary database for reads")
        
        # Define database schema
        define_schema()
        
        # Commit schema changes
        db.commit()
        if db_read != db:
            db_read.commit()
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def define_schema() -> None:
    """Define the database schema using PyDAL."""
    
    # Users table
    db.define_table('users',
        Field('id', 'id'),
        Field('username', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('email', 'string', length=255, unique=True, requires=IS_EMAIL()),
        Field('password_hash', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('full_name', 'string', length=255),
        Field('role', 'string', length=50, default='user', 
              requires=IS_IN_SET(['admin', 'reporter', 'user'])),
        Field('is_active', 'boolean', default=True),
        Field('last_login', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='users.table'
    )
    
    # Clusters table
    db.define_table('clusters',
        Field('id', 'id'),
        Field('name', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('region', 'string', length=100),
        Field('datacenter', 'string', length=100),
        Field('status', 'string', length=50, default='active',
              requires=IS_IN_SET(['active', 'inactive', 'maintenance'])),
        Field('config', 'json'),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='clusters.table'
    )
    
    # Clients table
    db.define_table('clients',
        Field('id', 'id'),
        Field('client_id', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('name', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('type', 'string', length=50, 
              requires=IS_IN_SET(['native', 'docker', 'mobile'])),
        Field('user_id', 'reference users', ondelete='CASCADE'),
        Field('cluster_id', 'reference clusters', ondelete='CASCADE'),
        Field('status', 'string', length=50, default='active',
              requires=IS_IN_SET(['active', 'inactive', 'suspended'])),
        Field('public_key', 'text'),
        Field('config', 'json'),
        Field('tunnel_mode', 'string', length=20, default='full',
              requires=IS_IN_SET(['full', 'split'])),
        Field('split_tunnel_routes', 'json'),  # List of routes for split tunnel mode (domains, IPv4/IPv6 addresses and CIDRs)
        Field('last_seen', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='clients.table'
    )
    
    # Firewall rules table
    db.define_table('firewall_rules',
        Field('id', 'id'),
        Field('user_id', 'reference users', ondelete='CASCADE'),
        Field('rule_type', 'string', length=50,
              requires=IS_IN_SET(['domain', 'ip', 'ip_range', 'url_pattern', 'protocol_rule'])),
        Field('name', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('description', 'text'),
        Field('action', 'string', length=20, default='allow',
              requires=IS_IN_SET(['allow', 'deny'])),
        Field('direction', 'string', length=20, default='both',
              requires=IS_IN_SET(['inbound', 'outbound', 'both'])),
        Field('priority', 'integer', default=100),
        Field('src_ip', 'string', length=100),
        Field('dst_ip', 'string', length=100),
        Field('protocol', 'string', length=20),
        Field('src_port', 'string', length=100),
        Field('dst_port', 'string', length=100),
        Field('domain', 'string', length=255),
        Field('url_pattern', 'text'),
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='firewall_rules.table'
    )
    
    # VRF (Virtual Routing and Forwarding) table
    db.define_table('vrfs',
        Field('id', 'id'),
        Field('name', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('description', 'text'),
        Field('rd', 'string', length=100, unique=True, requires=IS_NOT_EMPTY()),  # Route Distinguisher
        Field('ip_ranges', 'json'),  # List of IP ranges
        Field('area_type', 'string', length=50, default='normal',
              requires=IS_IN_SET(['normal', 'stub', 'nssa', 'backbone'])),
        Field('area_id', 'string', length=50),
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='vrfs.table'
    )
    
    # OSPF configuration table
    db.define_table('ospf_config',
        Field('id', 'id'),
        Field('vrf_id', 'reference vrfs', ondelete='CASCADE'),
        Field('area_id', 'string', length=50, requires=IS_NOT_EMPTY()),
        Field('area_type', 'string', length=50, default='normal',
              requires=IS_IN_SET(['normal', 'stub', 'nssa', 'backbone'])),
        Field('networks', 'json'),  # List of networks to advertise
        Field('interfaces', 'json'),  # List of interfaces in this area
        Field('auth_type', 'string', length=50, default='none',
              requires=IS_IN_SET(['none', 'simple', 'md5'])),
        Field('auth_key', 'string', length=255),
        Field('hello_interval', 'integer', default=10),
        Field('dead_interval', 'integer', default=40),
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='ospf_config.table'
    )
    
    # Port configurations table
    db.define_table('port_configs',
        Field('id', 'id'),
        Field('headend_id', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('cluster_id', 'reference clusters', ondelete='CASCADE'),
        Field('tcp_ranges', 'text'),
        Field('udp_ranges', 'text'),
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='port_configs.table'
    )
    
    # Port ranges table
    db.define_table('port_ranges',
        Field('id', 'id'),
        Field('port_config_id', 'reference port_configs', ondelete='CASCADE'),
        Field('start_port', 'integer', requires=IS_INT_IN_RANGE(1, 65536)),
        Field('end_port', 'integer', requires=IS_INT_IN_RANGE(1, 65536)),
        Field('protocol', 'string', length=10, requires=IS_IN_SET(['tcp', 'udp'])),
        Field('description', 'text'),
        Field('enabled', 'boolean', default=True),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='port_ranges.table'
    )
    
    # Certificates table
    db.define_table('certificates',
        Field('id', 'id'),
        Field('cert_type', 'string', length=50,
              requires=IS_IN_SET(['client', 'server', 'ca'])),
        Field('subject', 'string', length=500),
        Field('issuer', 'string', length=500),
        Field('serial_number', 'string', length=100, unique=True),
        Field('not_before', 'datetime'),
        Field('not_after', 'datetime'),
        Field('certificate_pem', 'text'),
        Field('private_key_pem', 'text'),
        Field('client_id', 'reference clients'),
        Field('revoked', 'boolean', default=False),
        Field('revoked_at', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='certificates.table'
    )
    
    # Sessions table for web authentication
    db.define_table('sessions',
        Field('id', 'id'),
        Field('session_id', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('user_id', 'reference users', ondelete='CASCADE'),
        Field('ip_address', 'string', length=45),
        Field('user_agent', 'text'),
        Field('expires_at', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        migrate='sessions.table'
    )
    
    # JWT tokens table
    db.define_table('jwt_tokens',
        Field('id', 'id'),
        Field('token_id', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('user_id', 'reference users', ondelete='CASCADE'),
        Field('token_type', 'string', length=50, 
              requires=IS_IN_SET(['access', 'refresh'])),
        Field('expires_at', 'datetime'),
        Field('revoked', 'boolean', default=False),
        Field('revoked_at', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        migrate='jwt_tokens.table'
    )

def get_db() -> DAL:
    """Get the primary database instance for write operations."""
    if db is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return db

def get_read_db() -> DAL:
    """Get the read database instance (read replica if available, otherwise primary)."""
    if db_read is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return db_read

def close_database() -> None:
    """Close database connections."""
    global db, db_read
    
    if db:
        db.close()
        db = None
    
    if db_read and db_read != db:
        db_read.close()
    db_read = None
    
    logger.info("Database connections closed")