"""Read only the signed-in Bilibili account's own favorites, one page at a time."""
import asyncio
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import User, get_current_user
from api.routers.cookies import BILIBILI_HEADERS, _netscape_to_header
from config import USE_SUPABASE

router = APIRouter()


async def _api(client, path, **params):
    try:
        response = await client.get("https://api.bilibili.com" + path, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Could not read Bilibili favorites. Please retry shortly.") from None
    if not isinstance(payload, dict):
        raise HTTPException(502, "Bilibili returned an unexpected response. Please retry.")
    if payload.get("code") in (-101, -111):
        raise HTTPException(409, "Bilibili login expired. Reconnect Bilibili in Settings.")
    if payload.get("code") != 0:
        raise HTTPException(502, "Bilibili could not return favorites. Please retry shortly.")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise HTTPException(502, "Bilibili returned an unexpected response. Please retry.")
    return data


async def _folders(client):
    account = await _api(client, "/x/web-interface/nav")
    if not account.get("isLogin") or not account.get("mid"):
        raise HTTPException(409, "Bilibili login expired. Reconnect Bilibili in Settings.")
    data = await _api(client, "/x/v3/fav/folder/created/list-all", up_mid=account["mid"])
    return [{"id":int(row["id"]), "title":row.get("title") or "Favorites", "count":row.get("media_count", 0)} for row in data.get("list") or []]


async def _cookie_header(user):
    if USE_SUPABASE and not user:
        raise HTTPException(401, "Authentication required")
    from cookie_manager import get_cookie_manager
    manager = get_cookie_manager(user.id if user else None)
    cookie = await asyncio.to_thread(manager.get_cookie, "bilibili")
    header = _netscape_to_header(cookie or "")
    if not header:
        raise HTTPException(409, "Connect Bilibili in Settings to browse your favorites.")
    return {**BILIBILI_HEADERS, "Cookie":header}


@router.get("")
async def list_folders(user: Optional[User] = Depends(get_current_user)):
    headers = await _cookie_header(user)
    async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
        return {"folders":await _folders(client)}


@router.get("/{folder_id}")
async def list_favorites(folder_id: int, page: int = Query(1, ge=1, le=10000), user: Optional[User] = Depends(get_current_user)):
    headers = await _cookie_header(user)
    async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
        folders = await _folders(client)
        if not any(folder["id"] == folder_id for folder in folders):
            raise HTTPException(404, "Favorite folder not found in your connected account")
        data = await _api(client, "/x/v3/fav/resource/list", media_id=folder_id, pn=page, ps=20, order="mtime", platform="web")
    videos = []
    for media in data.get("medias") or []:
        bvid = str(media.get("bvid") or "")
        available = bool(re.fullmatch(r"BV[A-Za-z0-9]{10}", bvid)) and media.get("title") not in {"已失效视频", "视频已失效"}
        videos.append({"bvid":bvid, "title":media.get("title") or "Unavailable video",
                       "url":f"https://www.bilibili.com/video/{bvid}" if available else "",
                       "thumbnail":media.get("cover") or "", "duration":media.get("duration") or 0,
                       "available":available, "uploader":(media.get("upper") or {}).get("name") or ""})
    from video_task_db import get_video_task_db
    existing = await asyncio.to_thread(get_video_task_db().get_existing_urls, [v["url"] for v in videos if v["available"]], user.id if user else None, True)
    for video in videos:
        video["imported"] = video["url"] in existing
    return {"videos":videos, "page":page, "has_more":bool(data.get("has_more"))}
