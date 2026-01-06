"""Configuration management for API server"""

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DatabaseConfig:
    """Database configuration"""
    db_type: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_pool_size: int

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Load from environment variables"""
        return cls(
            db_type=os.getenv('DB_TYPE', 'postgres'),
            db_host=os.getenv('DB_HOST', 'localhost'),
            db_port=int(os.getenv('DB_PORT', '5432')),
            db_name=os.getenv('DB_NAME', 'tobogganing'),
            db_user=os.getenv('DB_USER', 'postgres'),
            db_password=os.getenv('DB_PASSWORD', ''),
            db_pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
        )


@dataclass(slots=True, frozen=True)
class RedisConfig:
    """Redis configuration"""
    redis_host: str
    redis_port: int
    redis_password: str
    redis_db: int

    @classmethod
    def from_env(cls) -> 'RedisConfig':
        """Load from environment variables"""
        return cls(
            redis_host=os.getenv('REDIS_HOST', 'localhost'),
            redis_port=int(os.getenv('REDIS_PORT', '6379')),
            redis_password=os.getenv('REDIS_PASSWORD', ''),
            redis_db=int(os.getenv('REDIS_DB', '0')),
        )


@dataclass(slots=True, frozen=True)
class JWTConfig:
    """JWT configuration"""
    secret_key: str
    security_password_salt: str
    token_expiry_seconds: int
    refresh_token_expiry_seconds: int

    @classmethod
    def from_env(cls) -> 'JWTConfig':
        """Load from environment variables"""
        return cls(
            secret_key=os.getenv('SECRET_KEY', 'dev-secret-key'),
            security_password_salt=os.getenv('SECURITY_PASSWORD_SALT', 'dev-salt'),
            token_expiry_seconds=int(os.getenv('TOKEN_EXPIRY_SECONDS', '3600')),
            refresh_token_expiry_seconds=int(os.getenv('REFRESH_TOKEN_EXPIRY_SECONDS', '86400')),
        )


@dataclass(slots=True, frozen=True)
class GRPCConfig:
    """gRPC configuration"""
    grpc_host: str
    grpc_port: int

    @classmethod
    def from_env(cls) -> 'GRPCConfig':
        """Load from environment variables"""
        return cls(
            grpc_host=os.getenv('GRPC_HOST', '0.0.0.0'),
            grpc_port=int(os.getenv('GRPC_PORT', '50051')),
        )


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Main application configuration"""
    flask_env: str
    flask_debug: bool
    api_host: str
    api_port: int
    database: DatabaseConfig
    redis: RedisConfig
    jwt: JWTConfig
    grpc: GRPCConfig

    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Load from environment variables"""
        return cls(
            flask_env=os.getenv('FLASK_ENV', 'development'),
            flask_debug=os.getenv('FLASK_DEBUG', 'True').lower() == 'true',
            api_host=os.getenv('API_HOST', '0.0.0.0'),
            api_port=int(os.getenv('API_PORT', '5000')),
            database=DatabaseConfig.from_env(),
            redis=RedisConfig.from_env(),
            jwt=JWTConfig.from_env(),
            grpc=GRPCConfig.from_env(),
        )
