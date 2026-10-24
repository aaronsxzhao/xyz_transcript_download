"""A created Notion page must remain discoverable when its upload fails."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from api.routers import notion


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [
    HTTPException(502, 'Batch 2 was rejected'),
    httpx.ReadTimeout('private transport detail'),
    RuntimeError('private transport detail'),
])
async def test_partial_upload_reports_the_created_page_and_never_recreates_it(failure):
    create = AsyncMock(return_value=('created', 'https://notion.so/created'))
    append = AsyncMock(side_effect=failure)
    with patch.object(notion, '_create_notion_page', create), patch.object(notion, '_append_notion_blocks', append):
        with pytest.raises(HTTPException) as raised:
            await notion._export_note_content(object(), 'test-key', 'parent', 'Title', [])
    assert raised.value.status_code == (504 if isinstance(failure, httpx.TimeoutException) else 502)
    assert 'https://notion.so/created' in raised.value.detail
    assert 'was created' in raised.value.detail
    assert 'before exporting again' in raised.value.detail
    assert 'private transport detail' not in raised.value.detail
    create.assert_awaited_once()
    append.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejected_creation_is_not_claimed_to_have_created_a_page():
    with patch.object(notion, '_create_notion_page', AsyncMock(side_effect=HTTPException(401, 'Invalid Notion API key'))), \
         patch.object(notion, '_append_notion_blocks', AsyncMock()) as append:
        with pytest.raises(HTTPException) as raised:
            await notion._export_note_content(object(), 'test-key', 'parent', 'Title', [])
    assert raised.value.status_code == 401
    assert raised.value.detail == 'Invalid Notion API key'
    append.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_receipt_requires_all_upload_batches():
    blocks = [{'type': 'paragraph', 'paragraph': {'rich_text': []}} for _ in range(205)]
    client = AsyncMock()
    client.post.return_value = httpx.Response(201, json={'id': 'created', 'url': 'https://notion.so/created'})
    client.patch.return_value = httpx.Response(200, json={})
    result = await notion._export_note_content(client, 'test-key', 'parent', 'Title', blocks)
    assert result == {'page_id': 'created', 'url': 'https://notion.so/created', 'title': 'Title'}
    assert [len(call.kwargs['json']['children']) for call in client.patch.await_args_list] == [100, 100, 5]


@pytest.mark.asyncio
async def test_a_rejected_later_batch_stops_upload_and_preserves_the_page_address():
    blocks = [{'type': 'paragraph', 'paragraph': {'rich_text': []}} for _ in range(205)]
    client = AsyncMock()
    client.post.return_value = httpx.Response(201, json={'id': 'created', 'url': 'https://notion.so/created'})
    client.patch.side_effect = [httpx.Response(200, json={}), httpx.Response(400, json={'message': 'Invalid block'})]
    with pytest.raises(HTTPException) as raised:
        await notion._export_note_content(client, 'test-key', 'parent', 'Title', blocks)
    assert 'Batch 2' in raised.value.detail
    assert 'https://notion.so/created' in raised.value.detail
    assert client.patch.await_count == 2
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_long_titles_are_split_without_losing_characters():
    client = AsyncMock()
    client.post.return_value = httpx.Response(201, json={'id': 'created'})
    title = 'A long title 中文 ' * 300
    await notion._create_notion_page(client, 'test-key', 'parent', title)
    parts = client.post.await_args.kwargs['json']['properties']['title']['title']
    assert all(len(item['text']['content']) <= 2000 for item in parts)
    assert ''.join(item['text']['content'] for item in parts) == title
