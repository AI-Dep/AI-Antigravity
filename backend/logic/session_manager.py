"""
Session-Based State Management for FA CS Automator

Replaces global in-memory variables with proper session management:
- Per-user session isolation
- Automatic session expiration and cleanup
- Memory-bounded storage with LRU eviction
- Optional Redis backend for horizontal scaling

This solves:
- Data isolation between users
- Memory leaks from accumulated data
- State persistence across restarts (with Redis)
- Horizontal scaling capability
"""

import os
import time
import asyncio
import logging
import json
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from collections import OrderedDict
from threading import Lock
import hashlib

logger = logging.getLogger(__name__)


# ==============================================================================
# SAFE JSON SERIALIZATION (Replaces pickle to prevent RCE vulnerabilities)
# ==============================================================================

class SessionJSONEncoder(json.JSONEncoder):
    """
    Safe JSON encoder for session data.

    Handles:
    - datetime/date objects -> ISO format strings
    - sets -> lists
    - Pydantic models (Asset) -> dict via .dict()
    - dataclasses -> dict
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        if isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        if isinstance(obj, set):
            return {"__type__": "set", "value": list(obj)}
        # Handle Pydantic models (like Asset)
        if hasattr(obj, 'dict') and callable(obj.dict):
            return {"__type__": "pydantic", "class": obj.__class__.__name__, "value": obj.dict()}
        # Handle dataclasses
        if hasattr(obj, '__dataclass_fields__'):
            return {"__type__": "dataclass", "class": obj.__class__.__name__, "value": asdict(obj)}
        return super().default(obj)


def session_json_decoder(dct: dict) -> Any:
    """
    Safe JSON decoder hook for session data.

    Reconstructs typed objects from their JSON representation.
    Only allows known safe types - prevents arbitrary code execution.
    """
    if "__type__" not in dct:
        return dct

    type_tag = dct["__type__"]
    value = dct.get("value")

    if type_tag == "datetime":
        return datetime.fromisoformat(value)
    if type_tag == "date":
        return date.fromisoformat(value)
    if type_tag == "set":
        return set(value)
    if type_tag == "pydantic":
        # Only reconstruct known Pydantic models
        class_name = dct.get("class")
        if class_name == "Asset":
            # Import here to avoid circular imports
            from backend.models.asset import Asset
            return Asset(**value)
        # Unknown Pydantic class - return as dict for safety
        logger.warning(f"Unknown Pydantic class in session: {class_name}")
        return value
    if type_tag == "dataclass":
        # For dataclasses, we just return the dict - caller reconstructs
        return value

    return dct


def serialize_session(session: 'SessionData') -> str:
    """Safely serialize SessionData to JSON string."""
    data = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "created_at": session.created_at,
        "last_accessed": session.last_accessed,
        "expires_at": session.expires_at,
        "assets": session.assets,
        "asset_id_counter": session.asset_id_counter,
        "approved_assets": session.approved_assets,
        "tab_analysis_result": session.tab_analysis_result,
        "last_upload_filename": session.last_upload_filename,
        "tax_config": session.tax_config,
        "facs_config": session.facs_config,
    }
    return json.dumps(data, cls=SessionJSONEncoder)


def deserialize_session(json_str: str) -> 'SessionData':
    """Safely deserialize JSON string to SessionData."""
    data = json.loads(json_str, object_hook=session_json_decoder)

    # Convert assets dict keys back to int (JSON only supports string keys)
    assets = {}
    if data.get("assets"):
        for key, value in data["assets"].items():
            assets[int(key)] = value

    return SessionData(
        session_id=data["session_id"],
        user_id=data.get("user_id"),
        created_at=data["created_at"],
        last_accessed=data["last_accessed"],
        expires_at=data["expires_at"],
        assets=assets,
        asset_id_counter=data.get("asset_id_counter", 0),
        approved_assets=data.get("approved_assets", set()),
        tab_analysis_result=data.get("tab_analysis_result"),
        last_upload_filename=data.get("last_upload_filename"),
        tax_config=data.get("tax_config", {}),
        facs_config=data.get("facs_config", {}),
    )

T = TypeVar('T')


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Session configuration
SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24"))
SESSION_MAX_ASSETS = int(os.environ.get("SESSION_MAX_ASSETS", "10000"))
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "1000"))
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes

# Redis configuration (optional)
REDIS_URL = os.environ.get("REDIS_URL")  # e.g., "redis://localhost:6379/0"


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class SessionData:
    """Data stored in a user session."""
    session_id: str
    user_id: Optional[str]
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime

    # Asset data (replaces global ASSET_STORE)
    assets: Dict[int, Any] = field(default_factory=dict)
    asset_id_counter: int = 0
    approved_assets: set = field(default_factory=set)

    # Tab analysis result
    tab_analysis_result: Optional[Any] = None
    last_upload_filename: Optional[str] = None

    # Tax configuration (replaces global TAX_CONFIG)
    tax_config: Dict[str, Any] = field(default_factory=lambda: {
        "tax_year": datetime.now().year,
        "de_minimis_threshold": 2500,
        "has_afs": False,
        "bonus_rate": None,
        "section_179_limit": None,
    })

    # FA CS configuration (replaces global FACS_CONFIG)
    facs_config: Dict[str, Any] = field(default_factory=lambda: {
        "remote_mode": True,
        "user_confirmed_connected": False,
        "export_path": None,
        "asset_number_start": 1,  # Starting number for new FA CS Asset #s
    })

    def touch(self):
        """Update last accessed time."""
        self.last_accessed = datetime.utcnow()

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        return {
            "session_id": self.session_id,
            "asset_count": len(self.assets),
            "approved_count": len(self.approved_assets),
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "tax_year": self.tax_config.get("tax_year"),
        }


# ==============================================================================
# LRU CACHE FOR SESSIONS
# ==============================================================================

class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache with size limit.
    Evicts least recently used items when full.
    """

    def __init__(self, max_size: int):
        self.max_size = max_size
        self._cache: OrderedDict[str, T] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: str, value: T) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value

            # Evict oldest if over capacity
            while len(self._cache) > self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                logger.info(f"Evicted session {oldest_key} (LRU)")

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._cache.keys())

    def values(self) -> List[T]:
        with self._lock:
            return list(self._cache.values())

    def __len__(self) -> int:
        return len(self._cache)


# ==============================================================================
# SESSION MANAGER
# ==============================================================================

class SessionManager:
    """
    Manages user sessions with automatic cleanup.

    Features:
    - Per-user session isolation
    - Automatic expiration
    - LRU eviction when memory limit reached
    - Optional SQLite backend for persistence (single-server)
    - Optional Redis backend for scaling (multi-server)

    Storage priority: Redis > SQLite > Memory
    """

    def __init__(self, use_redis: bool = None, use_sqlite: bool = None):
        self._use_redis = use_redis if use_redis is not None else bool(REDIS_URL)
        self._local_cache = LRUCache[SessionData](MAX_SESSIONS)
        self._redis_client = None
        self._sqlite_store = None
        self._use_sqlite = False
        self._cleanup_task = None
        self._last_cleanup = time.time()

        # Initialize Redis first (highest priority)
        if self._use_redis:
            self._init_redis()

        # Initialize SQLite if Redis not available and SQLite configured
        if not self._use_redis:
            self._init_sqlite(use_sqlite)

    def _init_redis(self):
        """Initialize Redis connection."""
        try:
            import redis
            self._redis_client = redis.from_url(REDIS_URL)
            self._redis_client.ping()
            logger.info("Connected to Redis for session storage")
        except ImportError:
            logger.warning("Redis package not installed, falling back to local storage")
            self._use_redis = False
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, falling back to local storage")
            self._use_redis = False

    def _init_sqlite(self, use_sqlite: bool = None):
        """Initialize SQLite session storage."""
        from backend.logic.session_sqlite import is_sqlite_enabled, get_sqlite_store

        # Check if SQLite is enabled via env var or explicit parameter
        should_use = use_sqlite if use_sqlite is not None else is_sqlite_enabled()

        if not should_use:
            return

        try:
            self._sqlite_store = get_sqlite_store()
            if self._sqlite_store:
                self._use_sqlite = True
                logger.info(f"SQLite session storage enabled: {self._sqlite_store.db_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite session storage: {e}")
            self._use_sqlite = False

    def _generate_session_id(self, user_id: Optional[str] = None) -> str:
        """Generate unique session ID."""
        import secrets
        base = f"{user_id or 'anon'}-{time.time()}-{secrets.token_hex(8)}"
        return hashlib.sha256(base.encode()).hexdigest()[:32]

    def create_session(self, user_id: Optional[str] = None) -> SessionData:
        """Create a new session."""
        session_id = self._generate_session_id(user_id)
        now = datetime.utcnow()

        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=SESSION_TTL_HOURS)
        )

        self._save_session(session)
        logger.info(f"Created session {session_id} for user {user_id or 'anonymous'}")

        return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID, returns None if expired or not found."""
        session = self._load_session(session_id)

        if session is None:
            return None

        if session.is_expired():
            self.delete_session(session_id)
            return None

        # Update last accessed
        session.touch()
        self._save_session(session)

        return session

    def get_or_create_session(self, session_id: Optional[str] = None, user_id: Optional[str] = None) -> SessionData:
        """Get existing session or create new one."""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session

        return self.create_session(user_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from all storage backends."""
        # Delete from Redis
        if self._use_redis and self._redis_client:
            try:
                self._redis_client.delete(f"session:{session_id}")
            except Exception as e:
                logger.error(f"Failed to delete session from Redis: {e}")

        # Delete from SQLite
        if self._use_sqlite and self._sqlite_store:
            try:
                self._sqlite_store.delete(session_id)
            except Exception as e:
                logger.error(f"Failed to delete session from SQLite: {e}")

        return self._local_cache.delete(session_id)

    def _save_session(self, session: SessionData) -> None:
        """Save session to storage (memory + persistent backend)."""
        # Always cache in memory for fast access
        self._local_cache.set(session.session_id, session)

        # Persist to Redis if available
        if self._use_redis and self._redis_client:
            try:
                ttl = int((session.expires_at - datetime.utcnow()).total_seconds())
                if ttl > 0:
                    # Use safe JSON serialization instead of pickle (prevents RCE)
                    data = serialize_session(session)
                    self._redis_client.setex(
                        f"session:{session.session_id}",
                        ttl,
                        data
                    )
            except Exception as e:
                logger.error(f"Failed to save session to Redis: {e}")

        # Persist to SQLite if available (and Redis not in use)
        elif self._use_sqlite and self._sqlite_store:
            try:
                data = serialize_session(session)
                self._sqlite_store.set(session.session_id, data, session.expires_at)
            except Exception as e:
                logger.error(f"Failed to save session to SQLite: {e}")

    def _load_session(self, session_id: str) -> Optional[SessionData]:
        """Load session from storage (cache -> persistent backend)."""
        # Try local cache first (fastest)
        session = self._local_cache.get(session_id)
        if session:
            return session

        # Try Redis (if available)
        if self._use_redis and self._redis_client:
            try:
                data = self._redis_client.get(f"session:{session_id}")
                if data:
                    # Use safe JSON deserialization instead of pickle (prevents RCE)
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    session = deserialize_session(data)
                    self._local_cache.set(session_id, session)
                    return session
            except Exception as e:
                logger.error(f"Failed to load session from Redis: {e}")

        # Try SQLite (if available and Redis not in use)
        if self._use_sqlite and self._sqlite_store:
            try:
                data = self._sqlite_store.get(session_id)
                if data:
                    session = deserialize_session(data)
                    self._local_cache.set(session_id, session)
                    return session
            except Exception as e:
                logger.error(f"Failed to load session from SQLite: {e}")

        return None

    async def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        removed = 0

        # Clean memory cache
        for session_id in self._local_cache.keys():
            session = self._local_cache.get(session_id)
            if session and session.is_expired():
                self.delete_session(session_id)
                removed += 1

        # Clean SQLite (has its own expiration logic)
        if self._use_sqlite and self._sqlite_store:
            try:
                sqlite_removed = self._sqlite_store.cleanup_expired()
                removed += sqlite_removed
            except Exception as e:
                logger.error(f"SQLite cleanup error: {e}")

        if removed > 0:
            logger.info(f"Cleaned up {removed} expired sessions")

        return removed

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        async def _cleanup_loop():
            while True:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                try:
                    await self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")

        self._cleanup_task = asyncio.create_task(_cleanup_loop())

    def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        sessions = self._local_cache.values()
        total_assets = sum(len(s.assets) for s in sessions)

        stats = {
            "total_sessions": len(sessions),
            "total_assets": total_assets,
            "max_sessions": MAX_SESSIONS,
            "session_ttl_hours": SESSION_TTL_HOURS,
            "using_redis": self._use_redis,
            "using_sqlite": self._use_sqlite,
            "storage_backend": "redis" if self._use_redis else ("sqlite" if self._use_sqlite else "memory"),
        }

        # Include SQLite-specific stats if enabled
        if self._use_sqlite and self._sqlite_store:
            try:
                sqlite_stats = self._sqlite_store.get_stats()
                stats["sqlite"] = sqlite_stats
            except Exception as e:
                logger.debug(f"Failed to get SQLite stats: {e}")

        return stats


# ==============================================================================
# GLOBAL INSTANCE
# ==============================================================================

_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


# ==============================================================================
# FASTAPI INTEGRATION
# ==============================================================================

async def get_session_from_request(request) -> SessionData:
    """
    FastAPI dependency to get session from request.

    Looks for session_id in:
    1. X-Session-ID header
    2. session_id query parameter
    3. Cookie

    Creates new session if not found.

    Usage:
        @app.get("/assets")
        async def get_assets(session: SessionData = Depends(get_session_from_request)):
            return list(session.assets.values())
    """
    manager = get_session_manager()

    # Try to get session ID from various sources
    session_id = (
        request.headers.get("X-Session-ID") or
        request.query_params.get("session_id") or
        request.cookies.get("session_id")
    )

    # Get user_id if authenticated
    user_id = getattr(request.state, 'user', None)
    if user_id and hasattr(user_id, 'user_id'):
        user_id = user_id.user_id

    session = manager.get_or_create_session(session_id, user_id)

    # Store session_id for response
    request.state.session_id = session.session_id

    return session


def add_session_to_response(response, session_id: str):
    """Add session ID to response headers and cookies."""
    response.headers["X-Session-ID"] = session_id
    # NOTE: samesite="none" is required for cross-origin requests between
    # different ports (e.g., frontend on :5173, backend on :8000).
    # secure=False is allowed for localhost in modern browsers.
    # In production with HTTPS, set secure=True.
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="none",
        secure=False  # Set to True in production with HTTPS
    )
    return response
