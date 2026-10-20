"""Authentication endpoints for Supabase."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from config import USE_SUPABASE, SUPABASE_URL
from api.auth import get_current_user, User, security
from api.supabase_client import get_supabase_client

router = APIRouter()


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordChangeRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class UserResponse(BaseModel):
    id: str
    email: str
    authenticated: bool


@router.get("/config")
def get_auth_config():
    """Get authentication configuration for frontend."""
    return {
        "supabase_enabled": USE_SUPABASE,
        "supabase_url": SUPABASE_URL if USE_SUPABASE else None,
    }


@router.post("/signup", response_model=AuthResponse)
def sign_up(data: SignUpRequest):
    """Register a new user."""
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail="Authentication not configured")
    
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    from api.passwords import validate_new_password
    validate_new_password(data.password)
    try:
        result = client.auth.sign_up({
            "email": data.email,
            "password": data.password
        })
        
        if result.user is None:
            raise HTTPException(status_code=400, detail="Failed to create user")
        
        session = result.session
        if session is None:
            # Email confirmation required
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=result.user.id,
                email=result.user.email or data.email
            )
        
        return AuthResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user_id=result.user.id,
            email=result.user.email or data.email
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/signin", response_model=AuthResponse)
def sign_in(data: SignInRequest):
    """Sign in an existing user."""
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail="Authentication not configured")
    
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    
    try:
        result = client.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
        
        if result.user is None or result.session is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return AuthResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            user_id=result.user.id,
            email=result.user.email or data.email
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post('/password-reset')
def request_password_reset(data: PasswordResetRequest):
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail='Password recovery requires an authenticated cloud installation.')
    import os
    from api.request_limits import check_limit
    check_limit('reset:' + data.email.lower(), 3, 900)
    # A fixed configured origin prevents redirect injection. Recovery fragments
    # are routed to /reset-password by the web app, including default-site links.
    redirect = os.getenv('PUBLIC_APP_URL', 'https://aipodcastsummary.online').rstrip('/') + '/'
    try:
        get_supabase_client().auth.reset_password_email(data.email, {'redirect_to': redirect})
    except Exception:
        raise HTTPException(status_code=503, detail='Password recovery is temporarily unavailable. Please try again shortly.')
    return {'message': 'If an account exists for this email, a password reset link will arrive shortly.'}


@router.post('/password')
def change_password(data: PasswordChangeRequest, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), user: User = Depends(get_current_user)):
    if not USE_SUPABASE or not credentials:
        raise HTTPException(status_code=401, detail='Open the recovery link from your email to set a new password.')
    from api.passwords import validate_new_password
    from api.supabase_client import get_user_client
    validate_new_password(data.password)
    try:
        get_user_client(credentials.credentials).auth.update_user({'password': data.password})
    except Exception:
        raise HTTPException(status_code=400, detail='This recovery link is invalid or expired. Request a new link.')
    return {'message': 'Password updated. Sign in with your new password.'}


@router.post("/signout")
def sign_out(user: User = Depends(get_current_user)):
    """Sign out the current user."""
    if not USE_SUPABASE:
        return {"message": "Signed out"}
    
    # Client-side will clear the token
    return {"message": "Signed out successfully"}


@router.post("/refresh", response_model=AuthResponse)
def refresh_token(data: RefreshRequest):
    """Refresh the access token."""
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail="Authentication not configured")
    
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    
    try:
        result = client.auth.refresh_session(data.refresh_token)
        
        if result.user is None or result.session is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        return AuthResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            user_id=result.user.id,
            email=result.user.email or ""
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserResponse)
def get_current_user_info(user: Optional[User] = Depends(get_current_user)):
    """Get the current user's information."""
    if not user:
        return UserResponse(id="", email="", authenticated=False)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        authenticated=True
    )
