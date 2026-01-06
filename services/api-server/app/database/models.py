"""Database models for Flask API Server using PyDAL."""

from datetime import datetime
from typing import Optional
from pydal import DAL, Field
from pydal.validators import IS_NOT_EMPTY, IS_EMAIL, IS_IN_SET, IS_INT_IN_RANGE


def define_schema(db: DAL) -> None:
    """Define the database schema using PyDAL.

    Args:
        db: PyDAL database instance to define schema on
    """

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

    # Clients table with new client_type field
    db.define_table('clients',
        Field('id', 'id'),
        Field('client_id', 'string', length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field('name', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('type', 'string', length=50,
              requires=IS_IN_SET(['native', 'docker', 'mobile'])),
        Field('client_type', 'string', length=50,
              requires=IS_IN_SET(['user', 'hypervisor_lxd', 'hypervisor_kvm', 'k8s_node', 'k8s_cluster'])),
        Field('user_id', 'reference users', ondelete='CASCADE'),
        Field('cluster_id', 'reference clusters', ondelete='CASCADE'),
        Field('status', 'string', length=50, default='active',
              requires=IS_IN_SET(['active', 'inactive', 'suspended'])),
        Field('public_key', 'text'),
        Field('config', 'json'),
        Field('tunnel_mode', 'string', length=20, default='full',
              requires=IS_IN_SET(['full', 'split'])),
        Field('split_tunnel_routes', 'json'),
        Field('last_seen', 'datetime'),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='clients.table'
    )

    # Initial secrets table for secret exchange
    db.define_table('initial_secrets',
        Field('id', 'id'),
        Field('client_id', 'reference clients', ondelete='CASCADE'),
        Field('secret_hash', 'string', length=255, requires=IS_NOT_EMPTY()),
        Field('expires_at', 'datetime', requires=IS_NOT_EMPTY()),
        Field('used', 'boolean', default=False),
        Field('created_at', 'datetime', default=datetime.now),
        Field('updated_at', 'datetime', default=datetime.now, update=datetime.now),
        migrate='initial_secrets.table'
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
        Field('rd', 'string', length=100, unique=True, requires=IS_NOT_EMPTY()),
        Field('ip_ranges', 'json'),
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
        Field('networks', 'json'),
        Field('interfaces', 'json'),
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
