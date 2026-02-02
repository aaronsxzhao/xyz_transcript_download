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

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import USE_SUPABASE, SUPABASE_JWT_SECRET, SUPABASE_URL

security = HTTPBearer(auto_error=False)


@dataclass
class User:
    """Authenticated user information."""
    id: str  # UUID
    email: str
    

def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Verify a Supabase JWT token and return the payload.
    Returns None if verification fails.
    """
    if not USE_SUPABASE:
        return None
    
    try:
        from jose import jwt, JWTError
        
        # Supabase uses HS256 algorithm with JWT secret
        # If JWT secret not provided, we verify via Supabase API
        if SUPABASE_JWT_SECRET:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated"
            )
            return payload
        else:
            # Fallback: verify via Supabase auth API
            from api.supabase_client import get_supabase_client
            client = get_supabase_client()
            if client:
                user = client.auth.get_user(token)
                if user and user.user:
                    return {
                        "sub": user.user.id,
                        "email": user.user.email
                    }
            return None
    except Exception:
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
