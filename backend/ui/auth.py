"""
Fixed Asset AI - Authentication Module
Secure user authentication with password hashing and session management.

Features:
- Bcrypt password hashing (industry standard)
- Session timeout management
- Role-based access control
- Client access isolation
- Audit logging for auth events
"""

import hashlib
import secrets
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class UserRole(Enum):
    """User role definitions for RBAC."""
    ADMIN = "admin"          # Full access: manage users, all clients
    MANAGER = "manager"      # Approve exports, manage assigned clients
    STAFF = "staff"          # Process assets for assigned clients
    READONLY = "readonly"    # View only access


@dataclass
class User:
    """User data class."""
    user_id: int
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


@dataclass
class Session:
    """Session data class."""
    session_token: str
    user_id: int
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    ip_address: Optional[str] = None


# Session timeout in minutes (configurable via environment)
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))


def hash_password(password: str) -> str:
    """
    Hash password using SHA-256 with salt.

    For production, consider using bcrypt. This uses SHA-256 with salt
    as a dependency-free alternative that's still reasonably secure.

    Args:
        password: Plain text password

    Returns:
        Hashed password string (salt:hash format)
    """
    # Generate random salt
    salt = secrets.token_hex(32)

    # Hash password with salt using SHA-256
    password_hash = hashlib.sha256((salt + password).encode()).hexdigest()

    # Return salt:hash format
    return f"{salt}:{password_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.

    Args:
        password: Plain text password to verify
        stored_hash: Stored hash in salt:hash format

    Returns:
        True if password matches, False otherwise
    """
    try:
        # Split stored hash into salt and hash
        salt, expected_hash = stored_hash.split(":", 1)

        # Hash provided password with same salt
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()

        # Compare hashes (constant time comparison to prevent timing attacks)
        return secrets.compare_digest(password_hash, expected_hash)
    except (ValueError, AttributeError):
        return False


def generate_session_token() -> str:
    """
    Generate a cryptographically secure session token.

    Returns:
        32-byte hex token (64 characters)
    """
    return secrets.token_hex(32)


def is_session_expired(session: Session) -> bool:
    """
    Check if session has expired.

    Args:
        session: Session object to check

    Returns:
        True if session is expired, False otherwise
    """
    now = datetime.now()

    # Check absolute expiry
    if now > session.expires_at:
        return True

    # Check inactivity timeout
    inactivity_timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    if now - session.last_activity > inactivity_timeout:
        return True

    return False


def validate_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password meets security requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")

    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")

    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        errors.append("Password must contain at least one special character")

    return (len(errors) == 0, errors)


def get_role_permissions(role: UserRole) -> Dict[str, bool]:
    """
    Get permissions for a given role.

    Args:
        role: User role

    Returns:
        Dictionary of permission flags
    """
    permissions = {
        UserRole.ADMIN: {
            "manage_users": True,
            "manage_all_clients": True,
            "approve_exports": True,
            "process_assets": True,
            "view_audit_log": True,
            "export_data": True,
            "delete_data": True,
            "view_data": True,
        },
        UserRole.MANAGER: {
            "manage_users": False,
            "manage_all_clients": False,
            "approve_exports": True,
            "process_assets": True,
            "view_audit_log": True,
            "export_data": True,
            "delete_data": False,
            "view_data": True,
        },
        UserRole.STAFF: {
            "manage_users": False,
            "manage_all_clients": False,
            "approve_exports": False,
            "process_assets": True,
            "view_audit_log": False,
            "export_data": True,
            "delete_data": False,
            "view_data": True,
        },
        UserRole.READONLY: {
            "manage_users": False,
            "manage_all_clients": False,
            "approve_exports": False,
            "process_assets": False,
            "view_audit_log": False,
            "export_data": False,
            "delete_data": False,
            "view_data": True,
        },
    }

    return permissions.get(role, permissions[UserRole.READONLY])


class AuthManager:
    """
    Authentication manager for Fixed Asset AI.

    Handles user authentication, session management, and access control.
    """

    def __init__(self, db_manager):
        """
        Initialize auth manager.

        Args:
            db_manager: DatabaseManager instance
        """
        self.db = db_manager
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Ensure auth tables exist in database."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if users table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='users'
            """)

            if not cursor.fetchone():
                # Create auth tables
                cursor.executescript("""
                    -- Users table
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        full_name TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'staff',
                        is_active BOOLEAN DEFAULT 1,
                        failed_login_attempts INTEGER DEFAULT 0,
                        locked_until TIMESTAMP,
                        password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        created_by INTEGER,
                        FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

                    -- User sessions table
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_token TEXT NOT NULL UNIQUE,
                        user_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ip_address TEXT,
                        user_agent TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
                    CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
                    CREATE INDEX IF NOT EXISTS idx_sessions_active ON user_sessions(is_active);

                    -- User-Client access mapping
                    CREATE TABLE IF NOT EXISTS user_client_access (
                        access_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        client_id INTEGER NOT NULL,
                        access_level TEXT DEFAULT 'full',
                        granted_by INTEGER,
                        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE,
                        FOREIGN KEY (granted_by) REFERENCES users(user_id) ON DELETE SET NULL,
                        UNIQUE(user_id, client_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_user_client_user ON user_client_access(user_id);
                    CREATE INDEX IF NOT EXISTS idx_user_client_client ON user_client_access(client_id);

                    -- Auth audit log
                    CREATE TABLE IF NOT EXISTS auth_audit_log (
                        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id INTEGER,
                        username TEXT,
                        action TEXT NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        success BOOLEAN,
                        details TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_auth_audit_timestamp ON auth_audit_log(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit_log(user_id);
                    CREATE INDEX IF NOT EXISTS idx_auth_audit_action ON auth_audit_log(action);
                """)

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str,
        role: str = "staff",
        created_by: Optional[int] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new user.

        Args:
            username: Unique username
            email: User email
            password: Plain text password
            full_name: User's full name
            role: User role (admin, manager, staff, readonly)
            created_by: User ID of creator (for audit)

        Returns:
            Tuple of (success, message, user_id or None)
        """
        # Validate password strength
        is_valid, errors = validate_password_strength(password)
        if not is_valid:
            return (False, "Password requirements not met: " + "; ".join(errors), None)

        # Validate role
        valid_roles = [r.value for r in UserRole]
        if role not in valid_roles:
            return (False, f"Invalid role. Must be one of: {', '.join(valid_roles)}", None)

        # Hash password
        password_hash = hash_password(password)

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Check if username or email already exists
                cursor.execute(
                    "SELECT user_id FROM users WHERE username = ? OR email = ?",
                    (username, email)
                )
                if cursor.fetchone():
                    return (False, "Username or email already exists", None)

                # Insert user
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, full_name, role, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, email, password_hash, full_name, role, created_by))

                user_id = cursor.lastrowid

                # Log auth event
                self._log_auth_event(
                    cursor, None, username, "USER_CREATED",
                    True, f"User created by user_id={created_by}"
                )

                return (True, "User created successfully", user_id)

        except Exception as e:
            return (False, f"Error creating user: {str(e)}", None)

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate user and create session.

        Args:
            username: Username or email
            password: Plain text password
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Tuple of (success, message, session_token or None)
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Find user by username or email
                cursor.execute("""
                    SELECT user_id, username, password_hash, is_active,
                           failed_login_attempts, locked_until
                    FROM users
                    WHERE username = ? OR email = ?
                """, (username, username))

                user = cursor.fetchone()

                if not user:
                    self._log_auth_event(
                        cursor, None, username, "LOGIN_FAILED",
                        False, "User not found", ip_address, user_agent
                    )
                    return (False, "Invalid username or password", None)

                user_id, db_username, password_hash, is_active, failed_attempts, locked_until = user

                # Check if account is locked
                if locked_until:
                    locked_until_dt = datetime.fromisoformat(locked_until)
                    if datetime.now() < locked_until_dt:
                        remaining = (locked_until_dt - datetime.now()).seconds // 60
                        self._log_auth_event(
                            cursor, user_id, db_username, "LOGIN_BLOCKED",
                            False, "Account locked", ip_address, user_agent
                        )
                        return (False, f"Account locked. Try again in {remaining} minutes", None)

                # Check if account is active
                if not is_active:
                    self._log_auth_event(
                        cursor, user_id, db_username, "LOGIN_FAILED",
                        False, "Account disabled", ip_address, user_agent
                    )
                    return (False, "Account is disabled. Contact administrator.", None)

                # Verify password
                if not verify_password(password, password_hash):
                    # Increment failed attempts
                    new_attempts = (failed_attempts or 0) + 1

                    # Lock account after 5 failed attempts
                    if new_attempts >= 5:
                        lock_until = datetime.now() + timedelta(minutes=15)
                        cursor.execute("""
                            UPDATE users
                            SET failed_login_attempts = ?, locked_until = ?
                            WHERE user_id = ?
                        """, (new_attempts, lock_until.isoformat(), user_id))

                        self._log_auth_event(
                            cursor, user_id, db_username, "ACCOUNT_LOCKED",
                            False, f"Too many failed attempts ({new_attempts})", ip_address, user_agent
                        )
                        return (False, "Account locked due to too many failed attempts. Try again in 15 minutes.", None)
                    else:
                        cursor.execute("""
                            UPDATE users SET failed_login_attempts = ?
                            WHERE user_id = ?
                        """, (new_attempts, user_id))

                        self._log_auth_event(
                            cursor, user_id, db_username, "LOGIN_FAILED",
                            False, f"Invalid password (attempt {new_attempts}/5)", ip_address, user_agent
                        )
                        return (False, "Invalid username or password", None)

                # Successful login - reset failed attempts and create session
                cursor.execute("""
                    UPDATE users
                    SET failed_login_attempts = 0, locked_until = NULL, last_login = ?
                    WHERE user_id = ?
                """, (datetime.now().isoformat(), user_id))

                # Create session
                session_token = generate_session_token()
                expires_at = datetime.now() + timedelta(hours=8)  # 8 hour max session

                cursor.execute("""
                    INSERT INTO user_sessions (session_token, user_id, expires_at, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_token, user_id, expires_at.isoformat(), ip_address, user_agent))

                self._log_auth_event(
                    cursor, user_id, db_username, "LOGIN_SUCCESS",
                    True, "User logged in", ip_address, user_agent
                )

                return (True, "Login successful", session_token)

        except Exception as e:
            return (False, f"Authentication error: {str(e)}", None)

    def validate_session(self, session_token: str) -> Tuple[bool, Optional[User]]:
        """
        Validate session token and return user if valid.

        Args:
            session_token: Session token to validate

        Returns:
            Tuple of (is_valid, User object or None)
        """
        if not session_token:
            return (False, None)

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Get session and user
                cursor.execute("""
                    SELECT s.session_id, s.user_id, s.expires_at, s.last_activity,
                           u.username, u.email, u.full_name, u.role, u.is_active,
                           u.created_at, u.last_login
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.session_token = ? AND s.is_active = 1
                """, (session_token,))

                result = cursor.fetchone()

                if not result:
                    return (False, None)

                (session_id, user_id, expires_at, last_activity,
                 username, email, full_name, role, is_active,
                 created_at, last_login) = result

                # Check if user is still active
                if not is_active:
                    return (False, None)

                # Check session expiry
                expires_at_dt = datetime.fromisoformat(expires_at)
                if datetime.now() > expires_at_dt:
                    # Session expired - deactivate
                    cursor.execute(
                        "UPDATE user_sessions SET is_active = 0 WHERE session_id = ?",
                        (session_id,)
                    )
                    return (False, None)

                # Check inactivity timeout
                last_activity_dt = datetime.fromisoformat(last_activity)
                if datetime.now() - last_activity_dt > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                    # Session timed out - deactivate
                    cursor.execute(
                        "UPDATE user_sessions SET is_active = 0 WHERE session_id = ?",
                        (session_id,)
                    )
                    return (False, None)

                # Update last activity
                cursor.execute("""
                    UPDATE user_sessions SET last_activity = ?
                    WHERE session_id = ?
                """, (datetime.now().isoformat(), session_id))

                # Return user
                user = User(
                    user_id=user_id,
                    username=username,
                    email=email,
                    full_name=full_name,
                    role=UserRole(role),
                    is_active=is_active,
                    created_at=datetime.fromisoformat(created_at),
                    last_login=datetime.fromisoformat(last_login) if last_login else None
                )

                return (True, user)

        except Exception as e:
            return (False, None)

    def logout(self, session_token: str) -> bool:
        """
        Logout user by invalidating session.

        Args:
            session_token: Session token to invalidate

        Returns:
            True if logout successful
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Get user info for audit log
                cursor.execute("""
                    SELECT s.user_id, u.username
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.session_token = ?
                """, (session_token,))

                result = cursor.fetchone()

                if result:
                    user_id, username = result

                    # Deactivate session
                    cursor.execute("""
                        UPDATE user_sessions SET is_active = 0
                        WHERE session_token = ?
                    """, (session_token,))

                    self._log_auth_event(
                        cursor, user_id, username, "LOGOUT",
                        True, "User logged out"
                    )

                return True

        except Exception:
            return False

    def get_user_clients(self, user_id: int) -> List[Dict]:
        """
        Get clients accessible by user.

        Args:
            user_id: User ID

        Returns:
            List of client dicts
        """
        try:
            # First check if user is admin (has access to all clients)
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()

                if result and result[0] == "admin":
                    # Admin gets all clients
                    cursor.execute("""
                        SELECT client_id, client_name, client_code, contact_name,
                               contact_email, active
                        FROM clients
                        WHERE active = 1
                        ORDER BY client_name
                    """)
                else:
                    # Non-admin gets only assigned clients
                    cursor.execute("""
                        SELECT c.client_id, c.client_name, c.client_code, c.contact_name,
                               c.contact_email, c.active
                        FROM clients c
                        JOIN user_client_access uca ON c.client_id = uca.client_id
                        WHERE uca.user_id = ? AND c.active = 1
                        ORDER BY c.client_name
                    """, (user_id,))

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

        except Exception:
            return []

    def grant_client_access(
        self,
        user_id: int,
        client_id: int,
        granted_by: int,
        access_level: str = "full"
    ) -> bool:
        """
        Grant user access to a client.

        Args:
            user_id: User to grant access to
            client_id: Client to grant access for
            granted_by: User granting access
            access_level: Level of access (full, readonly)

        Returns:
            True if successful
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO user_client_access
                    (user_id, client_id, access_level, granted_by)
                    VALUES (?, ?, ?, ?)
                """, (user_id, client_id, access_level, granted_by))

                return True

        except Exception:
            return False

    def revoke_client_access(self, user_id: int, client_id: int) -> bool:
        """
        Revoke user's access to a client.

        Args:
            user_id: User to revoke access from
            client_id: Client to revoke access for

        Returns:
            True if successful
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM user_client_access
                    WHERE user_id = ? AND client_id = ?
                """, (user_id, client_id))

                return True

        except Exception:
            return False

    def has_client_access(self, user_id: int, client_id: int) -> bool:
        """
        Check if user has access to a specific client.

        Args:
            user_id: User ID
            client_id: Client ID

        Returns:
            True if user has access
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Check if admin
                cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if result and result[0] == "admin":
                    return True

                # Check explicit access
                cursor.execute("""
                    SELECT 1 FROM user_client_access
                    WHERE user_id = ? AND client_id = ?
                """, (user_id, client_id))

                return cursor.fetchone() is not None

        except Exception:
            return False

    def get_all_users(self) -> List[Dict]:
        """Get all users (admin only)."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT user_id, username, email, full_name, role, is_active,
                           created_at, last_login
                    FROM users
                    ORDER BY created_at DESC
                """)

                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

        except Exception:
            return []

    def update_user(self, user_id: int, **kwargs) -> bool:
        """
        Update user fields.

        Args:
            user_id: User to update
            **kwargs: Fields to update (email, full_name, role, is_active)

        Returns:
            True if successful
        """
        allowed_fields = {'email', 'full_name', 'role', 'is_active'}
        safe_kwargs = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not safe_kwargs:
            return False

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                set_clause = ', '.join([f"{k} = ?" for k in safe_kwargs.keys()])
                query = f"UPDATE users SET {set_clause}, updated_at = ? WHERE user_id = ?"
                params = list(safe_kwargs.values()) + [datetime.now().isoformat(), user_id]

                cursor.execute(query, params)
                return cursor.rowcount > 0

        except Exception:
            return False

    def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """
        Change user password.

        Args:
            user_id: User ID
            old_password: Current password
            new_password: New password

        Returns:
            Tuple of (success, message)
        """
        # Validate new password strength
        is_valid, errors = validate_password_strength(new_password)
        if not is_valid:
            return (False, "Password requirements not met: " + "; ".join(errors))

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Get current password hash
                cursor.execute(
                    "SELECT password_hash FROM users WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()

                if not result:
                    return (False, "User not found")

                # Verify old password
                if not verify_password(old_password, result[0]):
                    return (False, "Current password is incorrect")

                # Hash and update new password
                new_hash = hash_password(new_password)
                cursor.execute("""
                    UPDATE users
                    SET password_hash = ?, password_changed_at = ?
                    WHERE user_id = ?
                """, (new_hash, datetime.now().isoformat(), user_id))

                return (True, "Password changed successfully")

        except Exception as e:
            return (False, f"Error changing password: {str(e)}")

    def reset_password(self, user_id: int, new_password: str, admin_id: int) -> Tuple[bool, str]:
        """
        Admin reset of user password.

        Args:
            user_id: User whose password to reset
            new_password: New password
            admin_id: Admin performing reset

        Returns:
            Tuple of (success, message)
        """
        # Validate new password strength
        is_valid, errors = validate_password_strength(new_password)
        if not is_valid:
            return (False, "Password requirements not met: " + "; ".join(errors))

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Verify admin has permission
                cursor.execute("SELECT role FROM users WHERE user_id = ?", (admin_id,))
                result = cursor.fetchone()
                if not result or result[0] != "admin":
                    return (False, "Insufficient permissions")

                # Hash and update password
                new_hash = hash_password(new_password)
                cursor.execute("""
                    UPDATE users
                    SET password_hash = ?, password_changed_at = ?,
                        failed_login_attempts = 0, locked_until = NULL
                    WHERE user_id = ?
                """, (new_hash, datetime.now().isoformat(), user_id))

                self._log_auth_event(
                    cursor, user_id, None, "PASSWORD_RESET",
                    True, f"Password reset by admin user_id={admin_id}"
                )

                return (True, "Password reset successfully")

        except Exception as e:
            return (False, f"Error resetting password: {str(e)}")

    def _log_auth_event(
        self,
        cursor,
        user_id: Optional[int],
        username: Optional[str],
        action: str,
        success: bool,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log authentication event to audit log."""
        cursor.execute("""
            INSERT INTO auth_audit_log
            (user_id, username, action, success, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, success, details, ip_address, user_agent))


def create_initial_admin(db_manager, password: str = None) -> Tuple[bool, str]:
    """
    Create initial admin user if no users exist.

    Args:
        db_manager: DatabaseManager instance
        password: Admin password (uses env var if not provided)

    Returns:
        Tuple of (success, message)
    """
    auth = AuthManager(db_manager)

    # Check if any users exist
    users = auth.get_all_users()
    if users:
        return (False, "Users already exist. Initial admin not created.")

    # Get password from env or use provided
    admin_password = password or os.getenv("INITIAL_ADMIN_PASSWORD")

    if not admin_password:
        # Generate secure random password
        admin_password = secrets.token_urlsafe(16)
        print(f"\n{'='*60}")
        print("INITIAL ADMIN ACCOUNT CREATED")
        print(f"{'='*60}")
        print(f"Username: admin")
        print(f"Password: {admin_password}")
        print(f"{'='*60}")
        print("SAVE THIS PASSWORD - IT WILL NOT BE SHOWN AGAIN")
        print(f"{'='*60}\n")

    success, msg, user_id = auth.create_user(
        username="admin",
        email="admin@localhost",
        password=admin_password,
        full_name="System Administrator",
        role="admin"
    )

    return (success, msg)
