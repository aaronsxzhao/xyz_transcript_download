"""
Authentication middleware for FastAPI with Supabase.
Validates JWT tokens and extracts user information.

Security Model:
- Local mode (USE_SUPABASE=False): No authentication required, single user
- Supabase mode (USE_SUPABASE=True): Authentication provides user_id for data isolation
  - All database queries filter by user_id
  - Unauthenticated requests get user_id=None, resulting in empty query results
  - Jobs, WebSocket broadcasts, and caches are all user-scoped
  - This ensures complete data isolation between users

Usage:
- get_current_user: Returns Optional[User], use for endpoints supporting both modes
- require_auth: Raises 401 if not authenticated, use for auth-only endpoints
"""

from typing import Optional
from dataclasses import dataclass
import threading
import time

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import USE_SUPABASE, SUPABASE_JWT_SECRET, SUPABASE_URL

security = HTTPBearer(auto_error=False)

# JWKS cache for ES256 verification
_jwks_cache = {
    "keys": None,
    "fetched_at": 0,
    "lock": threading.Lock()
}
_JWKS_CACHE_TTL = 3600  # Cache JWKS for 1 hour


@dataclass
class User:
    """Authenticated user information."""
    id: str  # UUID
    email: str


def _get_jwks_url() -> Optional[str]:
    """Get the JWKS URL for Supabase project."""
    if not SUPABASE_URL:
        return None
    # Supabase JWKS endpoint
    return f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> Optional[dict]:
    """Fetch JWKS from Supabase."""
    from logger import get_logger
    logger = get_logger("api.auth")
    
    jwks_url = _get_jwks_url()
    if not jwks_url:
        return None
    
    try:
        import urllib.request
        import json
        
        logger.info(f"[Auth] Fetching JWKS from {jwks_url}")
        with urllib.request.urlopen(jwks_url, timeout=10) as response:
            jwks = json.loads(response.read().decode())
            logger.info(f"[Auth] JWKS fetched successfully ({len(jwks.get('keys', []))} keys)")
            return jwks
    except Exception as e:
        logger.warning(f"[Auth] Failed to fetch JWKS: {e}")
        return None


def _get_cached_jwks(force_refresh: bool = False) -> Optional[dict]:
    """Get JWKS from cache or fetch if expired."""
    now = time.time()
    
    with _jwks_cache["lock"]:
        # Check if cache is valid
        if not force_refresh and _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < _JWKS_CACHE_TTL:
            return _jwks_cache["keys"]
        
        # Fetch new JWKS
        jwks = _fetch_jwks()
        if jwks:
            _jwks_cache["keys"] = jwks
            _jwks_cache["fetched_at"] = now
            return jwks
        
        # Return stale cache if fetch failed
        return _jwks_cache["keys"]


def _verify_with_jwks(token: str, jwks: dict) -> Optional[dict]:
    """Verify token using JWKS (ES256)."""
    from logger import get_logger
    logger = get_logger("api.auth")
    
    try:
        from jose import jwt, jwk
        from jose.exceptions import JWTError, JWKError
        
        # Get the key ID from token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "ES256")
        
        logger.debug(f"[Auth] Token header: kid={kid}, alg={alg}")
        
        # Find matching key in JWKS
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                signing_key = key
                break
        
        if not signing_key:
            logger.warning(f"[Auth] No matching key found for kid={kid}")
            return None
        
        # Convert JWK to public key and verify
        public_key = jwk.construct(signing_key)
        
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[alg],
            audience="authenticated"
        )
        
        logger.debug(f"[Auth] JWKS verification success: sub={payload.get('sub', 'N/A')}")
        return payload
        
    except Exception as e:
        logger.debug(f"[Auth] JWKS verification failed: {type(e).__name__}: {e}")
        return None


def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Verify a Supabase JWT token and return the payload.
    Returns None if verification fails.
    
    Verification order:
    1. JWKS/ES256 (fast, recommended for new Supabase projects)
    2. HS256 with legacy JWT secret (if configured)
    3. Supabase API fallback (slower, always works)
    """
    from logger import get_logger
    logger = get_logger("api.auth")
    
    if not USE_SUPABASE:
        logger.debug("verify_jwt_token: USE_SUPABASE is False, returning None")
        return None
    
    # Try JWKS/ES256 first (new Supabase projects use this)
    jwks = _get_cached_jwks()
    if jwks:
        payload = _verify_with_jwks(token, jwks)
        if payload:
            return payload
        
        # If verification failed, try refreshing JWKS (key might have rotated)
        logger.debug("[Auth] JWKS verification failed, refreshing keys")
        jwks = _get_cached_jwks(force_refresh=True)
        if jwks:
            payload = _verify_with_jwks(token, jwks)
            if payload:
                return payload
    
    # Try HS256 with legacy JWT secret (older projects)
    if SUPABASE_JWT_SECRET:
        try:
            from jose import jwt
            logger.debug("[Auth] Trying HS256 with legacy JWT secret")
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated"
            )
            logger.debug(f"[Auth] HS256 success: sub={payload.get('sub', 'N/A')}")
            return payload
        except Exception as e:
            logger.debug(f"[Auth] HS256 failed: {type(e).__name__}")
    
    # Last resort: Supabase API (slowest but always works)
    try:
        from api.supabase_client import get_supabase_client
        logger.debug("[Auth] Trying Supabase API fallback")
        client = get_supabase_client()
        if client:
            user = client.auth.get_user(token)
            if user and user.user:
                logger.debug(f"[Auth] Supabase API success: user_id={user.user.id}")
                return {
                    "sub": user.user.id,
                    "email": user.user.email
                }
    except Exception as e:
        logger.warning(f"[Auth] Supabase API failed: {type(e).__name__}: {e}")
    
    logger.warning("[Auth] All verification methods failed")
    return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    Dependency to get the current authenticated user.
    Returns None if not authenticated (for optional auth).
    """
    if not USE_SUPABASE:
        # If Supabase not configured, return a default user for local mode
        return User(id="local", email="local@localhost")
    
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = verify_jwt_token(token)
    
    if not payload:
        return None
    
    return User(
        id=payload.get("sub", ""),
        email=payload.get("email", "")
    )


async def require_auth(
    user: Optional[User] = Depends(get_current_user)
) -> User:
    """
    Dependency that requires authentication.
    Raises 401 if not authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def get_auth_header(request: Request) -> Optional[str]:
    """Extract the Bearer token from request headers."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


async def get_user_from_token_param(
    request: Request,
    token: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    Get user from either Authorization header OR query parameter.
    Useful for endpoints that open in new browser tabs (like HTML export).
    """
    if not USE_SUPABASE:
        return User(id="local", email="local@localhost")
    
    # Try header first
    if credentials:
        payload = verify_jwt_token(credentials.credentials)
        if payload:
            return User(id=payload.get("sub", ""), email=payload.get("email", ""))
    
    # Fall back to query parameter
    if token:
        payload = verify_jwt_token(token)
        if payload:
            return User(id=payload.get("sub", ""), email=payload.get("email", ""))
    
    return None
