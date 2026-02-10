"""
User Management System for SASEWaddle Manager
Supports role-based access control with admin and reporter roles
"""

import hashlib
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

import structlog
import bcrypt

logger = structlog.get_logger()

class UserRole(Enum):
    ADMIN = "admin"
    REPORTER = "reporter"

@dataclass
class User:
    id: str
    username: str
    email: str
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    password_hash: Optional[str] = None  # Not included in API responses

@dataclass 
class Session:
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

class UserManager:
    """Manages user authentication and authorization"""
    
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.session_timeout_hours = 8
        self._init_database()
        
    def _init_database(self):
        """Initialize SQLite database with user and session tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Create default admin user if none exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            self._create_default_admin(cursor)
        
        conn.commit()
        conn.close()
        
        logger.info("User database initialized")
    
    def _create_default_admin(self, cursor):
        """Create default admin user with secure random password"""
        admin_id = secrets.token_hex(16)
        # Generate secure password and hash it
        password = secrets.token_urlsafe(16)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
        """, (admin_id, "admin", "admin@sasewaddle.local", password_hash, "admin"))
        
        logger.warning("Created default admin user", 
                      username="admin", 
                      password=password,
                      message="SAVE THIS PASSWORD - it will not be shown again!")
    
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username/password"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, password_hash, role, is_active, created_at, last_login
                FROM users WHERE username = ? AND is_active = 1
            """, (username,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning("Authentication failed - user not found", username=username)
                return None
            
            user_id, username, email, password_hash, role, is_active, created_at, last_login = row
            
            # Verify password
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                logger.warning("Authentication failed - invalid password", username=username)
                return None
            
            # Update last login
            cursor.execute("""
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
            """, (user_id,))
            conn.commit()
            conn.close()
            
            user = User(
                id=user_id,
                username=username,
                email=email,
                role=UserRole(role),
                created_at=datetime.fromisoformat(created_at),
                last_login=datetime.now(),
                is_active=bool(is_active)
            )
            
            logger.info("User authenticated successfully", username=username, role=role)
            return user
            
        except Exception as e:
            logger.error("Authentication error", error=str(e))
            return None
    
    async def create_session(self, user: User, user_agent: str = None, ip_address: str = None) -> Session:
        """Create new session for authenticated user"""
        session_id = secrets.token_urlsafe(32)
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=self.session_timeout_hours)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO sessions (session_id, user_id, expires_at, user_agent, ip_address)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, user.id, expires_at.isoformat(), user_agent, ip_address))
            
            conn.commit()
            conn.close()
            
            session = Session(
                session_id=session_id,
                user_id=user.id,
                created_at=created_at,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address
            )
            
            logger.info("Session created", user_id=user.id, session_id=session_id[:8] + "...")
            return session
            
        except Exception as e:
            logger.error("Session creation error", error=str(e))
            raise
    
    async def validate_session(self, session_id: str) -> Optional[User]:
        """Validate session and return user if valid"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT s.user_id, s.expires_at, u.username, u.email, u.role, u.is_active,
                       u.created_at, u.last_login
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_id = ? AND u.is_active = 1
            """, (session_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            user_id, expires_at, username, email, role, is_active, created_at, last_login = row
            
            # Check if session is expired
            if datetime.fromisoformat(expires_at) < datetime.now():
                # Clean up expired session
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                conn.close()
                return None
            
            conn.close()
            
            return User(
                id=user_id,
                username=username,
                email=email,
                role=UserRole(role),
                created_at=datetime.fromisoformat(created_at),
                last_login=datetime.fromisoformat(last_login) if last_login else None,
                is_active=bool(is_active)
            )
            
        except Exception as e:
            logger.error("Session validation error", error=str(e))
            return None
    
    async def logout(self, session_id: str) -> bool:
        """Invalidate session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            if deleted:
                logger.info("Session invalidated", session_id=session_id[:8] + "...")
            
            return deleted
            
        except Exception as e:
            logger.error("Logout error", error=str(e))
            return False
    
    async def cleanup_expired_sessions(self):
        """Remove expired sessions from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")
            deleted = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info("Cleaned up expired sessions", count=deleted)
            
        except Exception as e:
            logger.error("Session cleanup error", error=str(e))
    
    async def create_user(self, username: str, email: str, password: str, role: UserRole) -> User:
        """Create new user (admin only)"""
        try:
            user_id = secrets.token_hex(16)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, email, password_hash, role.value))
            
            conn.commit()
            conn.close()
            
            user = User(
                id=user_id,
                username=username,
                email=email,
                role=role,
                created_at=datetime.now(),
                is_active=True
            )
            
            logger.info("User created", username=username, role=role.value)
            return user
            
        except sqlite3.IntegrityError as e:
            logger.error("User creation failed - duplicate", username=username, error=str(e))
            raise ValueError("Username or email already exists")
        except Exception as e:
            logger.error("User creation error", error=str(e))
            raise
    
    async def list_users(self) -> List[User]:
        """List all users (admin only)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, role, is_active, created_at, last_login
                FROM users ORDER BY created_at DESC
            """)
            
            users = []
            for row in cursor.fetchall():
                user_id, username, email, role, is_active, created_at, last_login = row
                users.append(User(
                    id=user_id,
                    username=username,
                    email=email,
                    role=UserRole(role),
                    created_at=datetime.fromisoformat(created_at),
                    last_login=datetime.fromisoformat(last_login) if last_login else None,
                    is_active=bool(is_active)
                ))
            
            conn.close()
            return users
            
        except Exception as e:
            logger.error("List users error", error=str(e))
            return []
    
    async def update_user_status(self, user_id: str, is_active: bool) -> bool:
        """Enable/disable user (admin only)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (is_active, user_id))
            updated = cursor.rowcount > 0
            
            if not is_active and updated:
                # Invalidate all sessions for disabled user
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            
            conn.commit()
            conn.close()
            
            if updated:
                logger.info("User status updated", user_id=user_id, is_active=is_active)
            
            return updated
            
        except Exception as e:
            logger.error("Update user status error", error=str(e))
            return False
    
    def has_permission(self, user: User, permission: str) -> bool:
        """Check if user has specific permission"""
        if user.role == UserRole.ADMIN:
            return True  # Admin has all permissions
        
        if user.role == UserRole.REPORTER:
            # Reporter has read-only permissions
            return permission in [
                "view_dashboard",
                "view_metrics", 
                "view_clients",
                "view_clusters",
                "view_status"
            ]
        
        return False
    
    def require_permission(self, user: User, permission: str):
        """Decorator helper to require specific permission"""
        if not self.has_permission(user, permission):
            raise PermissionError(f"User {user.username} lacks permission: {permission}")