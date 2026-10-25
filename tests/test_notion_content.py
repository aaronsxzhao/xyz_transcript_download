"""Notion transport limits must not remove or rewrite note content."""
from unittest.mock import patch

from starlette.requests import Request

from api.routers.notion import _prepare_export_blocks


def request():
    return Request({"type": "http", "scheme": "https", "server": ("notes.example", 443),
                    "path": "/api/notion/export-markdown", "root_path": "", "headers": [], "query_string": b""})


def test_code_is_unchanged_while_real_links_and_signed_images_are_normalized():
    code = "[Literal](#keep-this)\n![Example](/data/screenshots/sample.jpg)"
    blocks = _prepare_export_blocks(
        f"```md\n{code}\n```\n\n`[Literal](#keep-this)`\n\n[Chapter](#chapter)\n\n"
        "![Chart](/data/screenshots/chart.jpg?expires=123&signature=abc)\n\n"
        "[Page](/viewer/one)\n\n[External](https://example.com/source)", request())
    assert blocks[0]["code"]["rich_text"][0]["text"]["content"] == code
    inline = blocks[1]["paragraph"]["rich_text"][0]
    assert inline["text"]["content"] == "[Literal](#keep-this)"
    assert inline["annotations"]["code"] is True
    assert blocks[2]["paragraph"]["rich_text"][0]["text"] == {"content": "Chapter"}
    assert blocks[3]["image"]["external"]["url"] == "https://notes.example/data/screenshots/chart.jpg?expires=123&signature=abc"
    assert blocks[4]["paragraph"]["rich_text"][0]["text"]["link"]["url"] == "https://notes.example/viewer/one"
    assert blocks[5]["paragraph"]["rich_text"][0]["text"]["link"]["url"] == "https://example.com/source"


def test_long_paragraphs_and_code_keep_all_characters_in_valid_text_items():
    prose = "中🙂detail " * 750
    code = 'print("preserve all lines")\n' * 250
    blocks = _prepare_export_blocks(f"{prose}\n\n```python\n{code}```", request())
    assert len(blocks) == 2
    for block, expected in zip(blocks, [prose.rstrip(), code.rstrip()]):
        texts = block[block["type"]]["rich_text"]
        assert len(texts) > 1
        assert all(len(item["text"]["content"]) <= 2000 for item in texts)
        assert "".join(item["text"]["content"] for item in texts) == expected


def test_nested_rich_text_keeps_links_annotations_and_table_cells():
    text = {"type": "text", "text": {"content": "A" * 4500, "link": {"url": "/source"}}, "annotations": {"bold": True}}
    blocks = [{"type": "table", "table": {"children": [{"type": "table_row", "table_row": {"cells": [[text]]}}]}}]
    with patch("notion_markdown.to_notion", return_value=blocks):
        result = _prepare_export_blocks("table", request())
    cells = result[0]["table"]["children"][0]["table_row"]["cells"][0]
    assert "".join(item["text"]["content"] for item in cells) == "A" * 4500
    assert [len(item["text"]["content"]) for item in cells] == [2000, 2000, 500]
    assert all(item["annotations"] == {"bold": True} and item["text"]["link"] == {"url": "https://notes.example/source"} for item in cells)
    assert text["text"]["link"]["url"] == "/source"


def test_article_image_export_uses_stable_original_url_instead_of_expiring_reader_link():
    blocks=_prepare_export_blocks('![Chart](/api/article-image?url=https%3A%2F%2Fblog.example%2Fchart.png&expires=1&signature=abc&size=article)',request())
    assert blocks[0]['image']['external']['url']=='https://blog.example/chart.png'
