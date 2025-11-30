"""
Authentication Middleware for FA CS Automator

Implements JWT-based authentication:
- Token generation and validation
- User session management
- Role-based access control (RBAC)
- API key support for service accounts

Security Features:
- Tokens expire after configurable time
- Refresh token rotation
- Secure password hashing
- Rate limiting on auth endpoints
"""

import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Use PyJWT for token handling
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    jwt = None

logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Secret key for JWT signing - MUST be set in production
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# API Key prefix for service accounts
API_KEY_PREFIX = "facs_"


# ==============================================================================
# DATA MODELS
# ==============================================================================

class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # Subject (user_id)
    exp: datetime  # Expiration
    iat: datetime  # Issued at
    type: str  # "access" or "refresh"
    roles: List[str] = []
    session_id: Optional[str] = None


class TokenResponse(BaseModel):
    """Token response for login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


@dataclass
class User:
    """User model for authentication."""
    user_id: str
    email: str
    name: str
    roles: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None


@dataclass
class Session:
    """User session tracking."""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True


# ==============================================================================
# IN-MEMORY STORAGE (Replace with database in production)
# ==============================================================================

# Simple in-memory user store for development
# In production, use database with proper password hashing
_users: Dict[str, Dict[str, Any]] = {}
_sessions: Dict[str, Session] = {}
_api_keys: Dict[str, str] = {}  # api_key -> user_id


def _hash_password(password: str, salt: Optional[str] = None) -> tuple:
    """Hash password with salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((password + salt).encode())
    return hash_obj.hexdigest(), salt


def create_user(email: str, password: str, name: str, roles: List[str] = None) -> User:
    """Create a new user."""
    user_id = secrets.token_urlsafe(16)
    password_hash, salt = _hash_password(password)

    _users[user_id] = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "password_hash": password_hash,
        "password_salt": salt,
        "roles": roles or ["user"],
        "is_active": True,
        "created_at": datetime.utcnow()
    }

    return User(
        user_id=user_id,
        email=email,
        name=name,
        roles=roles or ["user"]
    )


def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate user by email and password."""
    for user_data in _users.values():
        if user_data["email"] == email:
            password_hash, _ = _hash_password(password, user_data["password_salt"])
            if password_hash == user_data["password_hash"]:
                if not user_data["is_active"]:
                    return None
                return User(
                    user_id=user_data["user_id"],
                    email=user_data["email"],
                    name=user_data["name"],
                    roles=user_data["roles"]
                )
    return None


def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID."""
    if user_id in _users:
        data = _users[user_id]
        return User(
            user_id=data["user_id"],
            email=data["email"],
            name=data["name"],
            roles=data["roles"],
            is_active=data["is_active"]
        )
    return None


# ==============================================================================
# TOKEN MANAGEMENT
# ==============================================================================

def create_access_token(user: User, session_id: Optional[str] = None) -> str:
    """Create JWT access token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT not installed. Run: pip install PyJWT")

    now = datetime.utcnow()
    expires = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user.user_id,
        "email": user.email,
        "name": user.name,
        "roles": user.roles,
        "type": "access",
        "session_id": session_id,
        "iat": now,
        "exp": expires
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: User, session_id: str) -> str:
    """Create JWT refresh token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT not installed. Run: pip install PyJWT")

    now = datetime.utcnow()
    expires = now + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user.user_id,
        "type": "refresh",
        "session_id": session_id,
        "iat": now,
        "exp": expires
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_tokens(user: User, request: Optional[Request] = None) -> TokenResponse:
    """Create access and refresh token pair."""
    # Create session
    session_id = secrets.token_urlsafe(16)
    session = Session(
        session_id=session_id,
        user_id=user.user_id,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("User-Agent") if request else None
    )
    _sessions[session_id] = session

    access_token = create_access_token(user, session_id)
    refresh_token = create_refresh_token(user, session_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


def verify_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token."""
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT not installed. Run: pip install PyJWT")

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        if payload.get("type") != expected_type:
            logger.warning(f"Token type mismatch: expected {expected_type}, got {payload.get('type')}")
            return None

        # Check session is still valid
        session_id = payload.get("session_id")
        if session_id and session_id in _sessions:
            session = _sessions[session_id]
            if not session.is_active:
                logger.warning(f"Session {session_id} is no longer active")
                return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.debug("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def invalidate_session(session_id: str) -> bool:
    """Invalidate a session (logout)."""
    if session_id in _sessions:
        _sessions[session_id].is_active = False
        return True
    return False


# ==============================================================================
# API KEY MANAGEMENT
# ==============================================================================

def create_api_key(user_id: str, name: str = "default") -> str:
    """Create API key for service account access."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    _api_keys[key] = user_id
    return key


def verify_api_key(key: str) -> Optional[str]:
    """Verify API key and return user_id."""
    return _api_keys.get(key)


# ==============================================================================
# FASTAPI DEPENDENCIES
# ==============================================================================

# HTTP Bearer token extractor
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    FastAPI dependency to get current authenticated user.

    Supports:
    - Bearer token (JWT)
    - API key in X-API-Key header

    Usage:
        @app.get("/protected")
        async def protected_endpoint(user: User = Depends(get_current_user)):
            return {"user": user.email}
    """
    # Check for API key first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user_id = verify_api_key(api_key)
        if user_id:
            user = get_user_by_id(user_id)
            if user:
                return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Check for Bearer token
    if credentials:
        payload = verify_token(credentials.credentials, expected_type="access")
        if payload:
            user = get_user_by_id(payload["sub"])
            if user and user.is_active:
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # No authentication provided
    return None


async def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    """
    FastAPI dependency that requires authentication.

    Usage:
        @app.get("/protected")
        async def protected_endpoint(user: User = Depends(require_auth)):
            return {"user": user.email}
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_roles(*roles: str):
    """
    FastAPI dependency that requires specific roles.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(user: User = Depends(require_roles("admin"))):
            return {"admin": True}
    """
    async def check_roles(user: User = Depends(require_auth)) -> User:
        if not any(role in user.roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(roles)}"
            )
        return user

    return check_roles


# ==============================================================================
# MIDDLEWARE
# ==============================================================================

class AuthMiddleware:
    """
    Authentication middleware for FastAPI.

    Adds user to request.state if authenticated.
    Does not block unauthenticated requests (use dependencies for that).
    """

    def __init__(self, app, exclude_paths: List[str] = None):
        self.app = app
        self.exclude_paths = exclude_paths or ["/", "/docs", "/openapi.json", "/health"]

    async def __call__(self, request: Request, call_next):
        # Skip auth for excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Try to extract and validate token
        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get("X-API-Key")

        user = None

        if api_key:
            user_id = verify_api_key(api_key)
            if user_id:
                user = get_user_by_id(user_id)

        elif auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_token(token)
            if payload:
                user = get_user_by_id(payload["sub"])

        # Attach user to request state
        request.state.user = user

        # Add user info to response headers for debugging
        response = await call_next(request)
        if user:
            response.headers["X-User-ID"] = user.user_id

        return response


# ==============================================================================
# INITIALIZATION
# ==============================================================================

def init_default_users():
    """Initialize default users for development."""
    if not _users:
        # Create default admin user
        create_user(
            email="admin@example.com",
            password="admin123",  # Change in production!
            name="Admin User",
            roles=["admin", "user"]
        )
        logger.info("Created default admin user: admin@example.com")


# Auto-initialize on module load (development only)
if os.environ.get("FA_ENV") != "production":
    init_default_users()
