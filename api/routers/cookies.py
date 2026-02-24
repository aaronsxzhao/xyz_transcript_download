"""Cookie management endpoints for video platform authentication."""
import asyncio
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
    msg = poll_data.get("message", "")
    logger.info(f"BiliBili QR poll: code={code}, message={msg}")

    # BiliBili QR poll codes:
    #   0     = login confirmed (success)
    #   86090 = scanned, waiting for user to confirm on phone
    #   86101 = not scanned yet (waiting)
    #   86038 = QR code expired

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
    """Convert a cookie dict to Netscape cookies.txt format for yt-dlp (BiliBili)."""
    return _cookies_dict_to_netscape(cookies, ".bilibili.com")


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


def _cookies_dict_to_netscape(cookies: dict, domain: str) -> str:
    """Convert a cookie dict to Netscape cookies.txt format for yt-dlp."""
    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        lines.append(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def _simple_cookie_to_netscape(cookie_str: str, domain: str) -> str:
    """Convert a simple 'key=val; key=val' cookie string to Netscape format."""
    cookies = {}
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, val = pair.split("=", 1)
            cookies[key.strip()] = val.strip()
    return _cookies_dict_to_netscape(cookies, domain)


# ==================== Douyin QR Code Login ====================

DOUYIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json, text/plain, */*",
}

_douyin_sessions: dict[str, dict] = {}


@router.get("/douyin/qr/generate")
async def douyin_qr_generate(user: Optional[User] = Depends(get_current_user)):
    """Generate a Douyin QR code for login."""
    try:
        async with httpx.AsyncClient(
            headers=DOUYIN_HEADERS,
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                "https://sso.douyin.com/get_qrcode/",
                params={
                    "aid": "6383",
                    "service": "https://www.douyin.com",
                },
            )
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Douyin API timed out")
    except Exception as e:
        logger.error(f"Douyin QR generate error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to reach Douyin: {type(e).__name__}")

    inner = data.get("data", {})
    token = inner.get("token", "")
    qr_url = inner.get("qrcode_index_url", "")

    if not token or not qr_url:
        logger.error(f"Douyin QR unexpected response: {data}")
        raise HTTPException(status_code=502, detail="Failed to generate Douyin QR code")

    session_cookies = {}
    for header_val in resp.headers.get_list("set-cookie"):
        parts = header_val.split(";")[0].strip()
        if "=" in parts:
            k, v = parts.split("=", 1)
            session_cookies[k.strip()] = v.strip()

    _douyin_sessions[token] = {
        "created_at": time.time(),
        "session_cookies": session_cookies,
    }

    return {"qr_url": qr_url, "token": token}


@router.get("/douyin/qr/poll")
async def douyin_qr_poll(
    token: str,
    user: Optional[User] = Depends(get_current_user),
):
    """Poll Douyin QR code login status."""
    if token not in _douyin_sessions:
        raise HTTPException(status_code=404, detail="QR session not found")

    session = _douyin_sessions[token]
    if time.time() - session["created_at"] > 180:
        _douyin_sessions.pop(token, None)
        return {"status": "expired", "message": "QR code expired"}

    sess_cookies = session.get("session_cookies", {})
    cookie_header = "; ".join(f"{k}={v}" for k, v in sess_cookies.items())

    try:
        headers = {**DOUYIN_HEADERS, "Cookie": cookie_header}
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                "https://sso.douyin.com/check_qrconnect/",
                params={
                    "aid": "6383",
                    "token": token,
                    "service": "https://www.douyin.com",
                },
            )
            data = resp.json()
    except httpx.TimeoutException:
        return {"status": "waiting", "message": "Douyin API slow, retrying..."}
    except Exception as e:
        logger.warning(f"Douyin QR poll error: {e}")
        return {"status": "waiting", "message": "Network error, retrying..."}

    inner = data.get("data", {})
    status_code = str(inner.get("status", ""))

    if status_code == "3":
        redirect_url = inner.get("redirect_url", "")
        all_cookies = dict(sess_cookies)

        for header_val in resp.headers.get_list("set-cookie"):
            parts = header_val.split(";")[0].strip()
            if "=" in parts:
                k, v = parts.split("=", 1)
                all_cookies[k.strip()] = v.strip()

        if redirect_url:
            try:
                redir_headers = {**DOUYIN_HEADERS, "Cookie": "; ".join(f"{k}={v}" for k, v in all_cookies.items())}
                async with httpx.AsyncClient(
                    headers=redir_headers,
                    timeout=10.0,
                    follow_redirects=True,
                ) as redir_client:
                    redir_resp = await redir_client.get(redirect_url)
                    for header_val in redir_resp.headers.get_list("set-cookie"):
                        parts = header_val.split(";")[0].strip()
                        if "=" in parts:
                            k, v = parts.split("=", 1)
                            all_cookies[k.strip()] = v.strip()
            except Exception as e:
                logger.warning(f"Douyin redirect follow failed: {e}")

        if all_cookies:
            cookie_str = _cookies_dict_to_netscape(all_cookies, ".douyin.com")
            from cookie_manager import get_cookie_manager
            get_cookie_manager().set_cookie("douyin", cookie_str)
            logger.info(f"Douyin QR login success, saved {len(all_cookies)} cookies")

        _douyin_sessions.pop(token, None)
        return {"status": "success", "message": "Login successful, cookies saved"}

    elif status_code == "2":
        return {"status": "scanned", "message": "Scanned, waiting for confirmation"}
    elif status_code == "5":
        _douyin_sessions.pop(token, None)
        return {"status": "expired", "message": "QR code expired"}
    else:
        return {"status": "waiting", "message": "Waiting for scan"}


# ==================== Auto-import from browser ====================

SUPPORTED_BROWSERS = ["chrome", "firefox", "edge", "safari", "opera", "brave", "chromium", "vivaldi"]


class BrowserImportRequest(BaseModel):
    platform: str
    browser: str = "chrome"


@router.post("/import-browser")
async def import_browser_cookies(data: BrowserImportRequest, user: Optional[User] = Depends(get_current_user)):
    """Extract cookies from a local browser using yt-dlp's cookies_from_browser.

    Works when the server runs on the same machine as the browser (local mode).
    On cloud/Docker deployments, returns a clear error suggesting file upload instead.
    """
    domain = PLATFORM_DOMAINS.get(data.platform)
    if not domain:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {data.platform}")
    if data.browser.lower() not in SUPPORTED_BROWSERS:
        raise HTTPException(status_code=400, detail=f"Unsupported browser: {data.browser}")

    import tempfile
    import os
    cookie_file = tempfile.mktemp(suffix=".txt")

    try:
        import yt_dlp
        opts = {
            "cookiesfrombrowser": (data.browser.lower(),),
            "cookiefile": cookie_file,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            pass

        if not os.path.exists(cookie_file):
            raise HTTPException(status_code=500, detail="Cookie extraction produced no output")

        raw = open(cookie_file, "r", encoding="utf-8").read()
        raw_lines = raw.strip().splitlines()

        filtered = ["# Netscape HTTP Cookie File", ""]
        count = 0
        bare_domain = domain.lstrip(".")
        for line in raw_lines:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                ld = parts[0].lstrip(".")
                if bare_domain in ld or ld in bare_domain:
                    filtered.append(line)
                    count += 1

        if count == 0:
            return {
                "success": False,
                "message": f"No {data.platform} cookies found in {data.browser}. "
                           f"Make sure you are logged in to {data.platform} in {data.browser}.",
                "cookie_count": 0,
            }

        netscape = "\n".join(filtered) + "\n"
        from cookie_manager import get_cookie_manager
        get_cookie_manager().set_cookie(data.platform, netscape)
        logger.info(f"Browser import ({data.browser}) for {data.platform}: {count} cookies saved")
        return {
            "success": True,
            "message": f"Imported {count} cookies for {data.platform} from {data.browser}",
            "cookie_count": count,
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="yt-dlp not available")
    except Exception as e:
        err = str(e)
        if "no suitable" in err.lower() or "could not find" in err.lower() or "browser" in err.lower():
            return {
                "success": False,
                "message": f"Could not access {data.browser} cookies. "
                           f"If running on a remote server, use 'Upload cookies.txt' instead. "
                           f"If running locally, make sure {data.browser} is installed.",
                "cookie_count": 0,
            }
        logger.error(f"Browser cookie import failed: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": f"Failed to extract cookies: {type(e).__name__}: {str(e)[:200]}",
            "cookie_count": 0,
        }
    finally:
        if os.path.exists(cookie_file):
            os.unlink(cookie_file)


# ==================== Cookie Helper (simple string conversion) ====================

PLATFORM_DOMAINS = {
    "bilibili": ".bilibili.com",
    "youtube": ".youtube.com",
    "douyin": ".douyin.com",
    "kuaishou": ".kuaishou.com",
}


class SimpleCookieUpdate(BaseModel):
    platform: str
    cookie_string: str


@router.post("/save-simple")
async def save_simple_cookie(data: SimpleCookieUpdate, user: Optional[User] = Depends(get_current_user)):
    """Accept a simple 'key=val; key=val' cookie string and save it in Netscape format."""
    domain = PLATFORM_DOMAINS.get(data.platform)
    if not domain:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {data.platform}")
    if not data.cookie_string.strip():
        raise HTTPException(status_code=400, detail="Cookie string is empty")

    netscape = _simple_cookie_to_netscape(data.cookie_string, domain)
    from cookie_manager import get_cookie_manager
    get_cookie_manager().set_cookie(data.platform, netscape)
    return {"message": f"Cookies saved for {data.platform}"}


@router.post("/upload-file")
async def upload_cookie_file(
    platform: str = Form(...),
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Accept a Netscape cookies.txt file upload and save it for the given platform.

    Browser extensions like 'Get cookies.txt LOCALLY' export this format,
    which includes httpOnly cookies that document.cookie cannot access.
    """
    domain = PLATFORM_DOMAINS.get(platform)
    if not domain:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be a text file (cookies.txt)")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Cookie file is empty")

    lines = text.strip().splitlines()
    filtered_lines = ["# Netscape HTTP Cookie File", ""]
    cookie_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # #HttpOnly_ prefix marks httpOnly cookies — these are valid entries, not comments
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            line_domain = parts[0]
            if domain.lstrip(".") in line_domain or line_domain.lstrip(".") in domain.lstrip("."):
                filtered_lines.append(line)
                cookie_count += 1

    if cookie_count == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No cookies found for {platform} (domain {domain}) in the uploaded file. "
                   f"Make sure you exported cookies from the correct website.",
        )

    netscape = "\n".join(filtered_lines) + "\n"
    from cookie_manager import get_cookie_manager
    get_cookie_manager().set_cookie(platform, netscape)
    logger.info(f"Uploaded cookies.txt for {platform}: {cookie_count} cookies saved")
    return {"message": f"Saved {cookie_count} cookies for {platform}", "cookie_count": cookie_count}


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
