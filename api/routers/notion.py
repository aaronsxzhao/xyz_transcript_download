"""Notion integration endpoints for exporting video notes."""
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from api.auth import get_current_user, User
from config import NOTION_API_KEY
from logger import get_logger

logger = get_logger("notion")

router = APIRouter()

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_notion_key(x_notion_key: Optional[str] = Header(None)) -> str:
    key = x_notion_key or NOTION_API_KEY
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Notion API key not configured. Add it in Settings.",
        )
    return key


def _notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    title_prop = props.get("title", {})
    if not title_prop:
        for v in props.values():
            if v.get("type") == "title":
                title_prop = v
                break
    title_items = title_prop.get("title", [])
    return "".join(t.get("plain_text", "") for t in title_items) if title_items else "Untitled"


def _extract_icon(page: dict) -> str:
    icon = page.get("icon")
    if not icon:
        return ""
    if icon.get("type") == "emoji":
        return icon.get("emoji", "")
    return ""


@router.get("/pages")
async def list_notion_pages(
    query: str = "",
    user: Optional[User] = Depends(get_current_user),
    x_notion_key: Optional[str] = Header(None),
):
    """Search Notion for accessible pages to use as export targets."""
    key = _get_notion_key(x_notion_key)

    body: dict = {
        "filter": {"value": "page", "property": "object"},
        "page_size": 50,
    }
    if query:
        body["query"] = query

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{NOTION_API_BASE}/search",
                headers=_notion_headers(key),
                json=body,
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Notion API key")
        if resp.status_code != 200:
            logger.warning(f"Notion search failed: {resp.status_code} {resp.text[:300]}")
            raise HTTPException(status_code=502, detail="Notion API error")

        data = resp.json()
        pages = []
        for page in data.get("results", []):
            if page.get("archived"):
                continue
            pages.append({
                "id": page["id"],
                "title": _extract_title(page),
                "icon": _extract_icon(page),
                "url": page.get("url", ""),
            })
        return {"pages": pages}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Notion API timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notion search error: {e}")
        raise HTTPException(status_code=502, detail=f"Notion error: {type(e).__name__}")


class ExportRequest(BaseModel):
    task_id: str
    parent_page_id: str


@router.post("/export")
async def export_to_notion(
    req: ExportRequest,
    user: Optional[User] = Depends(get_current_user),
    x_notion_key: Optional[str] = Header(None),
):
    """Export a video note to Notion as a sub-page under the selected parent."""
    key = _get_notion_key(x_notion_key)

    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = db.get_task(req.task_id, user_id)

    if not task:
        raise HTTPException(status_code=404, detail="Video task not found")

    markdown = task.get("markdown", "")
    if not markdown:
        raise HTTPException(status_code=400, detail="No note content to export")

    title = task.get("title", "Untitled Video Note")

    from notion_markdown import to_notion
    blocks = to_notion(markdown)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create sub-page under parent
            create_resp = await client.post(
                f"{NOTION_API_BASE}/pages",
                headers=_notion_headers(key),
                json={
                    "parent": {"type": "page_id", "page_id": req.parent_page_id},
                    "properties": {
                        "title": {
                            "title": [{"text": {"content": title}}]
                        }
                    },
                },
            )
            if create_resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid Notion API key")
            if create_resp.status_code != 200:
                detail = create_resp.json().get("message", create_resp.text[:300])
                logger.warning(f"Notion create page failed: {create_resp.status_code} {detail}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to create Notion page: {detail}",
                )

            page_data = create_resp.json()
            page_id = page_data["id"]
            page_url = page_data.get("url", "")

            # Append content blocks in batches of 100 (API limit)
            for i in range(0, len(blocks), 100):
                batch = blocks[i : i + 100]
                append_resp = await client.patch(
                    f"{NOTION_API_BASE}/blocks/{page_id}/children",
                    headers=_notion_headers(key),
                    json={"children": batch},
                )
                if append_resp.status_code not in (200, 201):
                    logger.warning(
                        f"Notion append blocks batch {i // 100} failed: "
                        f"{append_resp.status_code} {append_resp.text[:200]}"
                    )

        logger.info(f"Exported video note '{title}' to Notion: {page_url}")
        return {"url": page_url, "page_id": page_id, "title": title}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Notion API timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notion export error: {e}")
        raise HTTPException(status_code=502, detail=f"Notion export failed: {type(e).__name__}: {str(e)[:200]}")
