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

    logger.info(f"BiliBili QR generate response: code={data.get('code')}")

    if data.get("code") != 0:
        logger.error(f"BiliBili QR generate failed: {data}")
        raise HTTPException(status_code=502, detail="Failed to generate BiliBili QR code")

    qr_data = data["data"]
    qr_url = qr_data["url"]
    qrcode_key = qr_data["qrcode_key"]

    _qr_sessions[qrcode_key] = {"created_at": time.time(), "status": "pending"}
    logger.info(f"BiliBili QR generated: key={qrcode_key[:8]}..., url_len={len(qr_url)}")

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
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key},
            )
            data = resp.json()
            set_cookie_headers = resp.headers.get_list("set-cookie")
            logger.debug(f"BiliBili QR poll HTTP {resp.status_code}, "
                          f"set-cookie count: {len(set_cookie_headers)}")
    except httpx.TimeoutException:
        return {"status": "waiting", "message": "BiliBili API slow, retrying..."}
    except Exception as e:
        logger.warning(f"BiliBili QR poll error: {e}")
        return {"status": "waiting", "message": "Network error, retrying..."}

    poll_data = data.get("data", {})
    code = poll_data.get("code")
    msg = poll_data.get("message", "")
    logger.info(f"BiliBili QR poll: code={code}, message={msg}, raw_keys={list(poll_data.keys())}")

    # BiliBili QR poll codes:
    #   0     = login confirmed (success)
    #   86090 = scanned, waiting for user to confirm on phone
    #   86101 = not scanned yet (waiting)
    #   86038 = QR code expired

    if code == 0:
        refresh_url = poll_data.get("url", "")
        logger.info(f"BiliBili QR success — refresh_url present: {bool(refresh_url)}, "
                     f"url_len: {len(refresh_url)}")

        cookies_from_url = _extract_cookies_from_url(refresh_url)
        cookies_from_headers = _extract_cookies_from_headers(resp.headers)
        all_cookies = {**cookies_from_url, **cookies_from_headers}

        logger.info(f"BiliBili QR cookies — from_url: {list(cookies_from_url.keys())}, "
                     f"from_headers: {list(cookies_from_headers.keys())}, "
                     f"total: {len(all_cookies)}")

        has_sessdata = "SESSDATA" in all_cookies
        has_bili_jct = "bili_jct" in all_cookies
        logger.info(f"BiliBili QR critical cookies — SESSDATA: {has_sessdata}, "
                     f"bili_jct: {has_bili_jct}")

        if all_cookies:
            cookie_str = _cookies_to_netscape(all_cookies)
            from cookie_manager import get_cookie_manager
            mgr = get_cookie_manager()
            mgr.set_cookie("bilibili", cookie_str)
            logger.info(f"BiliBili QR login success, saved {len(all_cookies)} cookies: "
                         f"{list(all_cookies.keys())}")
        else:
            logger.warning("BiliBili QR login returned code=0 but NO cookies extracted!")

        _qr_sessions.pop(qrcode_key, None)
        saved_count = len(all_cookies)
        return {
            "status": "success",
            "message": f"Login successful, {saved_count} cookies saved"
                       + ("" if has_sessdata else " (WARNING: SESSDATA missing)"),
        }

    elif code == 86090:
        return {"status": "scanned", "message": "QR code scanned, waiting for confirmation"}
    elif code == 86038 or "过期" in msg or "expired" in msg.lower():
        _qr_sessions.pop(qrcode_key, None)
        return {"status": "expired", "message": "QR code expired"}
    else:
        logger.info(f"BiliBili QR poll — unhandled code={code}, message={msg}")
        return {"status": "waiting", "message": f"Waiting for scan (code: {code})"}


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
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


def _parse_netscape_cookies(netscape_str: str) -> list[dict]:
    cookies = []
    for line in netscape_str.splitlines():
        line = line.strip()
        if not line:
            continue
        http_only = False
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            http_only = True
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies.append({
                "domain": parts[0],
                "path": parts[2],
                "secure": parts[3].upper() == "TRUE",
                "expires": parts[4],
                "name": parts[5],
                "value": parts[6],
                "http_only": http_only,
            })
    return cookies


@router.get("/douyin/diagnose")
async def douyin_diagnose_cookie(user: Optional[User] = Depends(get_current_user)):
    """Inspect saved Douyin cookies and report whether they look strong enough."""
    from cookie_manager import get_cookie_manager

    raw = get_cookie_manager().get_cookie("douyin")
    if not raw:
        return {
            "has_cookie": False,
            "looks_usable": False,
            "message": "No Douyin cookies saved yet. Use browser cookie import for best results.",
            "present": [],
            "missing": ["msToken", "ttwid", "__ac_nonce", "__ac_signature", "passport_csrf_token", "s_v_web_id"],
            "cookie_count": 0,
            "domains": [],
        }

    parsed = _parse_netscape_cookies(raw)
    names = {c["name"] for c in parsed if c.get("name")}
    domains = sorted({c["domain"] for c in parsed if c.get("domain")})
    critical = ["msToken", "ttwid", "__ac_nonce", "__ac_signature", "passport_csrf_token", "s_v_web_id"]
    present = [name for name in critical if name in names]
    missing = [name for name in critical if name not in names]

    looks_usable = all(name in names for name in ("ttwid", "__ac_nonce", "__ac_signature", "s_v_web_id"))
    if "msToken" not in names:
        message = (
            "Douyin cookies are saved, but `msToken` is missing. "
            "That often means yt-dlp will still fail with 'fresh cookies needed'. "
            "Use browser cookie import from a browser where the video already opens."
        )
    elif not looks_usable:
        message = (
            "Douyin cookies are incomplete. Browser cookie import is recommended, "
            "and QR login is unreliable right now."
        )
    else:
        message = (
            "Douyin cookies look reasonably complete. If yt-dlp still fails, "
            "the app will try the browser fallback locally."
        )

    return {
        "has_cookie": True,
        "looks_usable": looks_usable,
        "message": message,
        "present": present,
        "missing": missing,
        "cookie_count": len(parsed),
        "domains": domains,
    }


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
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.douyin.com",
}

_douyin_sessions: dict[str, dict] = {}


def _parse_json_response(resp: httpx.Response, label: str) -> dict:
    """Parse JSON with better logging for upstream anti-bot/html responses."""
    try:
        return resp.json()
    except Exception as e:
        body_preview = resp.text[:300].replace("\n", " ").replace("\r", " ")
        logger.error(
            f"{label} returned non-JSON response: status={resp.status_code}, "
            f"content_type={resp.headers.get('content-type', '')}, body={body_preview!r}"
        )
        raise HTTPException(
            status_code=502,
            detail=f"{label} returned invalid response (HTTP {resp.status_code}). Douyin may be blocking the QR request right now.",
        ) from e


@router.get("/douyin/qr/generate")
async def douyin_qr_generate(user: Optional[User] = Depends(get_current_user)):
    """Generate a Douyin QR code for login."""
    try:
        request_variants = [
            DOUYIN_HEADERS,
            {
                **DOUYIN_HEADERS,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            },
        ]
        resp = None
        data = None
        for headers in request_variants:
            async with httpx.AsyncClient(
                headers=headers,
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
                data = _parse_json_response(resp, "Douyin QR endpoint")
                if data:
                    break
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Douyin API timed out")
    except HTTPException:
        raise
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
            data = _parse_json_response(resp, "Douyin QR poll endpoint")
    except httpx.TimeoutException:
        return {"status": "waiting", "message": "Douyin API slow, retrying..."}
    except HTTPException as e:
        return {"status": "waiting", "message": e.detail}
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

YOUTUBE_COOKIE_KEY_HINTS = {"SID", "SSID", "HSID", "APISID", "SAPISID", "LOGIN_INFO"}


def _domain_matches_platform(platform: str, line_domain: str) -> bool:
    normalized = (line_domain or "").strip().lower().lstrip(".")
    if not normalized:
        return False

    if platform == "youtube":
      if (
          normalized.endswith("youtube.com") or
          normalized.endswith("youtu.be") or
          normalized.endswith("google.com") or
          normalized.endswith("google.com.hk") or
          normalized.endswith("youtube-nocookie.com")
      ):
          return True
      return False

    domain = PLATFORM_DOMAINS.get(platform, "").lstrip(".")
    return bool(domain) and (domain in normalized or normalized in domain)


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

    if data.platform == "youtube":
        cookie_names = {
            part.split("=", 1)[0].strip()
            for part in data.cookie_string.split(";")
            if "=" in part
        }
        if not (cookie_names & YOUTUBE_COOKIE_KEY_HINTS):
            raise HTTPException(
                status_code=400,
                detail=(
                    "This YouTube cookie string does not include the critical auth cookies "
                    "(such as SID / SAPISID / LOGIN_INFO) that cloud downloads usually need. "
                    "Please use the cookies.txt file upload method from a logged-in YouTube browser session."
                ),
            )

    netscape = _simple_cookie_to_netscape(data.cookie_string, domain)
    from cookie_manager import get_cookie_manager
    try:
        get_cookie_manager().set_cookie(data.platform, netscape)
    except Exception as e:
        logger.error(f"Failed to save cookies for {data.platform}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save cookies: {e}. Please check your database configuration.",
        )
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
    cookie_names: set[str] = set()
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
            if _domain_matches_platform(platform, line_domain):
                filtered_lines.append(line)
                cookie_count += 1
                if parts[5]:
                    cookie_names.add(parts[5])

    if cookie_count == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No cookies found for {platform} (domain {domain}) in the uploaded file. "
                   f"Make sure you exported cookies from the correct website.",
        )

    if platform == "youtube" and not (cookie_names & YOUTUBE_COOKIE_KEY_HINTS):
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded YouTube cookies.txt file is missing the critical auth cookies "
                "(such as SID / SAPISID / LOGIN_INFO). Re-export cookies from a browser where "
                "YouTube is already logged in, using the cookies.txt extension."
            ),
        )

    netscape = "\n".join(filtered_lines) + "\n"
    from cookie_manager import get_cookie_manager
    try:
        get_cookie_manager().set_cookie(platform, netscape)
    except Exception as e:
        logger.error(f"Failed to save cookies for {platform}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save cookies: {e}. Please check your database configuration.",
        )
    logger.info(
        f"Uploaded cookies.txt for {platform}: {cookie_count} cookies saved, "
        f"key_sample={sorted(cookie_names)[:15]}"
    )
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
