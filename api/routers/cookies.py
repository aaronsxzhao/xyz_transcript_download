"""Cookie management endpoints for video platform authentication."""
import asyncio
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user, User
from logger import get_logger

logger = get_logger("cookies")

router = APIRouter()

_qr_sessions: dict[str, dict] = {}

BILIBILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


class CookieUpdate(BaseModel):
    platform: str
    cookie_data: str


@router.get("/bilibili/qr/generate")
async def bilibili_qr_generate(user: Optional[User] = Depends(get_current_user)):
    """Generate a BiliBili QR code for login."""
    try:
        async with httpx.AsyncClient(
            headers=BILIBILI_HEADERS,
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            )
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="BiliBili API timed out. Check your network or try again.")
    except Exception as e:
        logger.error(f"BiliBili QR generate error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to reach BiliBili: {type(e).__name__}")

    if data.get("code") != 0:
        raise HTTPException(status_code=502, detail="Failed to generate BiliBili QR code")

    qr_data = data["data"]
    qr_url = qr_data["url"]
    qrcode_key = qr_data["qrcode_key"]

    _qr_sessions[qrcode_key] = {"created_at": time.time(), "status": "pending"}

    return {
        "qr_url": qr_url,
        "qrcode_key": qrcode_key,
    }


@router.get("/bilibili/qr/poll")
async def bilibili_qr_poll(
    qrcode_key: str,
    user: Optional[User] = Depends(get_current_user),
):
    """Poll BiliBili QR code login status."""
    if qrcode_key not in _qr_sessions:
        raise HTTPException(status_code=404, detail="QR session not found")

    session = _qr_sessions[qrcode_key]
    if time.time() - session["created_at"] > 180:
        _qr_sessions.pop(qrcode_key, None)
        return {"status": "expired", "message": "QR code expired, please generate a new one"}

    try:
        async with httpx.AsyncClient(
            headers=BILIBILI_HEADERS,
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key},
            )
            data = resp.json()
    except httpx.TimeoutException:
        return {"status": "waiting", "message": "BiliBili API slow, retrying..."}
    except Exception as e:
        logger.warning(f"BiliBili QR poll error: {e}")
        return {"status": "waiting", "message": "Network error, retrying..."}

    poll_data = data.get("data", {})
    code = poll_data.get("code")
    logger.info(f"BiliBili QR poll: code={code}, message={poll_data.get('message', '')}")

    # BiliBili QR poll codes:
    #   0     = login confirmed (success)
    #   86090 = scanned, waiting for user to confirm on phone
    #   86101 = not scanned yet (waiting)
    #   86038 = QR code expired
    msg = poll_data.get("message", "")

    if code == 0:
        refresh_url = poll_data.get("url", "")
        cookies_from_url = _extract_cookies_from_url(refresh_url)
        cookies_from_headers = _extract_cookies_from_headers(resp.headers)
        all_cookies = {**cookies_from_url, **cookies_from_headers}

        if all_cookies:
            cookie_str = _cookies_to_netscape(all_cookies)
            from cookie_manager import get_cookie_manager
            mgr = get_cookie_manager()
            mgr.set_cookie("bilibili", cookie_str)
            logger.info(f"BiliBili QR login success, saved {len(all_cookies)} cookies")

        _qr_sessions.pop(qrcode_key, None)
        return {"status": "success", "message": "Login successful, cookies saved"}

    elif code == 86090:
        return {"status": "scanned", "message": "QR code scanned, waiting for confirmation"}
    elif code == 86038 or "过期" in msg or "expired" in msg.lower():
        _qr_sessions.pop(qrcode_key, None)
        return {"status": "expired", "message": "QR code expired"}
    else:
        return {"status": "waiting", "message": "Waiting for scan"}


def _extract_cookies_from_url(url: str) -> dict:
    """Extract cookie key-value pairs from BiliBili's redirect URL query params."""
    from urllib.parse import urlparse, parse_qs
    if not url:
        return {}
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    cookies = {}
    for key, values in params.items():
        if values:
            cookies[key] = values[0]
    return cookies


def _extract_cookies_from_headers(headers) -> dict:
    """Extract cookies from Set-Cookie response headers."""
    cookies = {}
    for header_val in headers.get_list("set-cookie"):
        parts = header_val.split(";")[0].strip()
        if "=" in parts:
            key, val = parts.split("=", 1)
            cookies[key.strip()] = val.strip()
    return cookies


def _cookies_to_netscape(cookies: dict) -> str:
    """Convert a cookie dict to Netscape cookies.txt format for yt-dlp."""
    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    return "\n".join(lines) + "\n"


@router.get("/bilibili/validate")
async def bilibili_validate_cookie(user: Optional[User] = Depends(get_current_user)):
    """Check if saved BiliBili cookies are still valid by calling a lightweight API."""
    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    cookie_str = mgr.get_cookie("bilibili")
    if not cookie_str:
        return {"valid": False, "reason": "no_cookie", "message": "Not logged in"}

    # Parse Netscape cookie file into a header string
    cookie_header = _netscape_to_header(cookie_str)
    if not cookie_header:
        return {"valid": False, "reason": "bad_format", "message": "Cookie format invalid"}

    try:
        headers = {**BILIBILI_HEADERS, "Cookie": cookie_header}
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
            data = resp.json()
        if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
            uname = data["data"].get("uname", "")
            return {"valid": True, "reason": "ok", "message": f"Logged in as {uname}"}
        return {"valid": False, "reason": "expired", "message": "Cookie expired, please re-login"}
    except Exception as e:
        logger.warning(f"BiliBili cookie validation error: {e}")
        return {"valid": False, "reason": "error", "message": f"Validation failed: {type(e).__name__}"}


def _netscape_to_header(netscape_str: str) -> str:
    """Convert Netscape cookie file format to a Cookie header string."""
    pairs = []
    for line in netscape_str.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


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
