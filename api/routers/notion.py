"""Notion integration endpoints for exporting video notes."""
import asyncio
import json
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel

from api.auth import get_current_user, User
from config import NOTION_API_KEY, USE_SUPABASE
from logger import get_logger

logger = get_logger("notion")

router = APIRouter()

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_notion_key(x_notion_key: Optional[str] = Header(None)) -> str:
    key = x_notion_key or (NOTION_API_KEY if not USE_SUPABASE else "")
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


def _extract_notion_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("message") or body.get("detail") or resp.text[:300]
    except Exception:
        pass
    return resp.text[:300]


def _prepare_export_blocks(markdown: str, request: Request) -> list[dict]:
    """Normalize actual Notion URLs and text limits without rewriting source code."""
    from notion_markdown import to_notion

    base_origin = str(request.base_url).rstrip("/")

    def normalize_url(url: str) -> str:
        if url.startswith('/api/article-image?'):
            from urllib.parse import parse_qs, urlsplit
            original = parse_qs(urlsplit(url).query).get('url', [''])[0]
            if original.startswith(('https://', 'http://')):
                return original
        if url.startswith("//"):
            return f"{request.url.scheme}:{url}"
        if url.startswith("/"):
            return f"{base_origin}{url}"
        return url

    def prepare(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                # Notion cannot navigate source-document fragment links. Keep
                # the label and its formatting, removing only the link itself.
                if (
                    key == "link"
                    and isinstance(item, dict)
                    and str(item.get("url", "")).startswith("#")
                ):
                    continue
                result[key] = (
                    normalize_url(item)
                    if key == "url" and isinstance(item, str)
                    else prepare(item)
                )
            return result
        if isinstance(value, list):
            result = []
            for item in value:
                item = prepare(item)
                text = (
                    item.get("text")
                    if isinstance(item, dict) and item.get("type") == "text"
                    else None
                )
                content = text.get("content") if isinstance(text, dict) else None
                if isinstance(content, str) and len(content) > 2000:
                    result.extend(
                        {**item, "text": {**text, "content": content[start:start + 2000]}}
                        for start in range(0, len(content), 2000)
                    )
                else:
                    result.append(item)
            return result
        return value

    return prepare(to_notion(markdown))


async def _create_notion_page(
    client: httpx.AsyncClient,
    key: str,
    parent_page_id: str,
    title: str,
) -> tuple[str, str]:
    create_resp = await client.post(
        f"{NOTION_API_BASE}/pages",
        headers=_notion_headers(key),
        json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title[start:start + 2000]}}
                              for start in range(0, len(title), 2000)]
                }
            },
        },
    )
    if create_resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Notion API key")
    if create_resp.status_code not in (200, 201):
        detail = _extract_notion_error(create_resp)
        logger.warning(f"Notion create page failed: {create_resp.status_code} {detail}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create Notion page: {detail}",
        )

    page_data = create_resp.json()
    return page_data["id"], page_data.get("url", "")


def _notion_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _notion_block_batches(blocks: list[dict]) -> list[list[dict]]:
    """Respect both Notion's 100-child and 500 KB JSON request limits."""
    batches = []
    batch = []
    envelope_size = len(b'{"children":[]}')
    size = envelope_size
    for block in blocks:
        block_size = len(_notion_json(block))
        if envelope_size + block_size > 500_000:
            raise HTTPException(400, "One section exceeds Notion's request size limit. Split that section or download Markdown instead. No Notion page has been created.")
        separator = int(bool(batch))
        if len(batch) == 100 or size + separator + block_size > 500_000:
            batches.append(batch)
            batch = []
            size = envelope_size
            separator = 0
        batch.append(block)
        size += separator + block_size
    if batch:
        batches.append(batch)
    return batches


async def _append_notion_blocks(
    client: httpx.AsyncClient,
    key: str,
    page_id: str,
    batches: list[list[dict]],
) -> None:
    for number, batch in enumerate(batches, 1):
        append_resp = await client.patch(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=_notion_headers(key),
            # Send the exact UTF-8 encoding used by the size calculation;
            # httpx versions differ in their default Unicode JSON encoding.
            content=_notion_json({"children": batch}),
        )
        if append_resp.status_code not in (200, 201):
            detail = _extract_notion_error(append_resp)
            logger.warning(
                f"Notion append blocks batch {number} failed: "
                f"{append_resp.status_code} {detail}"
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Failed to append all content to Notion. "
                    f"Batch {number} was rejected: {detail}"
                ),
            )


async def _export_note_content(
    client: httpx.AsyncClient, key: str, parent_page_id: str, title: str, blocks: list[dict]
) -> dict:
    # Validate every batch before creating a page; an oversized later section
    # must not leave behind an avoidable partial export.
    batches = _notion_block_batches(blocks)
    page_id, page_url = await _create_notion_page(client, key, parent_page_id, title)
    try:
        await _append_notion_blocks(client, key, page_id, batches)
    except Exception as error:
        reason = error.detail if isinstance(error, HTTPException) else (
            "Content upload timed out." if isinstance(error, httpx.TimeoutException)
            else "Content upload could not be confirmed."
        )
        logger.warning("Notion content upload incomplete: %s", type(error).__name__)
        raise HTTPException(
            status_code=504 if isinstance(error, httpx.TimeoutException) else 502,
            detail=(f"Notion page was created at {page_url or page_id}, but its content may be incomplete. "
                    f"{reason} Check this page before exporting again to avoid duplicates."),
        ) from error
    return {"url": page_url, "page_id": page_id, "title": title}


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


class ExportMarkdownRequest(BaseModel):
    markdown: str
    title: str
    parent_page_id: str


@router.post("/export")
async def export_to_notion(
    req: ExportRequest,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    x_notion_key: Optional[str] = Header(None),
):
    """Export a video note to Notion as a sub-page under the selected parent."""
    key = _get_notion_key(x_notion_key)

    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = await asyncio.to_thread(db.get_task, req.task_id, user_id)

    if not task:
        raise HTTPException(status_code=404, detail="Video task not found")

    markdown = task.get("markdown", "")
    from api.media import sign_media_urls
    markdown = sign_media_urls(markdown, req.task_id)
    if not markdown:
        raise HTTPException(status_code=400, detail="No note content to export")

    title = task.get("title", "Untitled Video Note")

    try:
        blocks = await asyncio.to_thread(_prepare_export_blocks, markdown, request)
        async with httpx.AsyncClient(timeout=60.0) as client:
            result = await _export_note_content(client, key, req.parent_page_id, title, blocks)

        logger.info("Exported video note to Notion: %s", result["page_id"])
        return result

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Notion page creation timed out. Check Notion before exporting again; a page may already exist.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Notion export could not be confirmed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Notion export could not be confirmed. Check Notion before exporting again.")


@router.post("/export-markdown")
async def export_markdown_to_notion(
    req: ExportMarkdownRequest,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    x_notion_key: Optional[str] = Header(None),
):
    """Export arbitrary markdown content to Notion as a sub-page."""
    key = _get_notion_key(x_notion_key)

    if not req.markdown.strip():
        raise HTTPException(status_code=400, detail="No content to export")

    title = req.title or "Untitled"

    try:
        blocks = await asyncio.to_thread(_prepare_export_blocks, req.markdown, request)
        async with httpx.AsyncClient(timeout=60.0) as client:
            result = await _export_note_content(client, key, req.parent_page_id, title, blocks)

        logger.info("Exported markdown to Notion: %s", result["page_id"])
        return result

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Notion page creation timed out. Check Notion before exporting again; a page may already exist.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Notion markdown export could not be confirmed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Notion export could not be confirmed. Check Notion before exporting again.")
