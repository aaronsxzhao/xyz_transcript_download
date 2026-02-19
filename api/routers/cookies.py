"""Cookie management endpoints for video platform authentication."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user, User

router = APIRouter()

class CookieUpdate(BaseModel):
    platform: str
    cookie_data: str


@router.get("/{platform}")
async def get_cookie(platform: str, user: Optional[User] = Depends(get_current_user)):
    """Get cookie status for a platform (does not return actual cookie data for security)."""
    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    cookie = mgr.get_cookie(platform)
    return {
        "platform": platform,
        "has_cookie": bool(cookie),
        "length": len(cookie),
    }


@router.post("")
async def update_cookie(data: CookieUpdate, user: Optional[User] = Depends(get_current_user)):
    """Set or update cookie for a platform."""
    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    mgr.set_cookie(data.platform, data.cookie_data)
    return {"message": f"Cookie updated for {data.platform}"}


@router.delete("/{platform}")
async def delete_cookie(platform: str, user: Optional[User] = Depends(get_current_user)):
    """Delete cookie for a platform."""
    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    deleted = mgr.delete_cookie(platform)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return {"message": f"Cookie deleted for {platform}"}


@router.get("")
async def list_cookies(user: Optional[User] = Depends(get_current_user)):
    """List all stored platform cookies."""
    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    return {"cookies": mgr.list_cookies()}
