"""Authentication endpoints for Supabase."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from config import USE_SUPABASE, SUPABASE_URL
from api.auth import get_current_user, User
from api.supabase_client import get_supabase_client

router = APIRouter()


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
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
async def get_auth_config():
    """Get authentication configuration for frontend."""
    return {
        "supabase_enabled": USE_SUPABASE,
        "supabase_url": SUPABASE_URL if USE_SUPABASE else None,
    }


@router.post("/signup", response_model=AuthResponse)
async def sign_up(data: SignUpRequest):
    """Register a new user."""
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail="Authentication not configured")
    
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    
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
async def sign_in(data: SignInRequest):
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


@router.post("/signout")
async def sign_out(user: User = Depends(get_current_user)):
    """Sign out the current user."""
    if not USE_SUPABASE:
        return {"message": "Signed out"}
    
    # Client-side will clear the token
    return {"message": "Signed out successfully"}


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(refresh_token: str):
    """Refresh the access token."""
    if not USE_SUPABASE:
        raise HTTPException(status_code=400, detail="Authentication not configured")
    
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    
    try:
        result = client.auth.refresh_session(refresh_token)
        
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
async def get_current_user_info(user: Optional[User] = Depends(get_current_user)):
    """Get the current user's information."""
    if not user:
        return UserResponse(id="", email="", authenticated=False)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        authenticated=True
    )
