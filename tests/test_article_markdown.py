import pytest
from article_markdown import repair_article_markdown, readable_article_task
from social_content import html_markdown

BROKEN = '[\n\n![Evidence](https://images.example/preview.jpg)\n\n](https://images.example/full.jpg)*Image credit: Author*'
FIXED = '[![Evidence](https://images.example/preview.jpg)](https://images.example/full.jpg)\n\n*Image credit: Author*'


def test_html_linked_image_is_one_valid_markdown_link_with_separate_caption():
    html = '<figure><a href="https://images.example/full.jpg"><img src="https://images.example/preview.jpg" alt="Evidence"></a><figcaption><em>Image credit: Author</em></figcaption></figure>'
    assert html_markdown(html, 'https://writer.substack.com/p/post') == FIXED


def test_multiblock_link_keeps_every_paragraph_and_destination():
    result = html_markdown('<a href="/p/detail"><p>First paragraph.</p><p>Final condition.</p></a>', 'https://writer.substack.com')
    assert 'First paragraph.' in result and 'Final condition.' in result
    assert '[Open linked source](https://writer.substack.com/p/detail)' in result
    assert '[\n\n' not in result


def test_lazy_images_missing_targets_and_nested_media_sources():
    result = html_markdown('<img src="data:image/gif;base64,AAAA" data-src="/real.jpg" alt="Evidence"><a>Original text</a><img><video><source src="https://media.example/clip.mp4"></video>', 'https://writer.substack.com/p/post')
    assert '![Evidence](https://writer.substack.com/real.jpg)' in result
    assert 'Original text' in result
    assert 'https://writer.substack.com/p/post' not in result
    assert '[Embedded media](https://media.example/clip.mp4)' in result


def test_legacy_image_repair_preserves_caption_and_is_idempotent():
    original = '# Original title\n\n' + BROKEN + '\n\nFull original final paragraph.'
    repaired = repair_article_markdown(original)
    assert repaired == original.replace(BROKEN, FIXED)
    assert repair_article_markdown(repaired) == repaired


@pytest.mark.parametrize('fence', ['```', '~~~~'])
def test_legacy_repair_leaves_code_examples_verbatim(fence):
    original = f'{fence}\n{BROKEN}\n{fence}\n\n{BROKEN}'
    assert repair_article_markdown(original) == f'{fence}\n{BROKEN}\n{fence}\n\n{FIXED}'


def test_legacy_repair_does_not_rewrite_prose_or_non_image_links():
    original = '[\n\nActual original prose.\n\n](https://source.example)\n\n[Normal](https://source.example)'
    assert repair_article_markdown(original) == original


def test_article_reads_do_not_modify_storage_or_ai_notes():
    task = {'platform':'substack','style':'original','markdown':BROKEN}
    assert readable_article_task(task)['markdown'] == FIXED
    assert task['markdown'] == BROKEN
    assert readable_article_task({**task,'style':'detailed'})['markdown'] == BROKEN


@pytest.mark.asyncio
async def test_task_api_and_version_return_readable_original_without_overwriting_database(client,mock_database):
    from video_task_db import VideoTaskDB
    db=VideoTaskDB(mock_database.db_path)
    task=db.create_task({'user_id':'local','platform':'substack','style':'original','url':'https://writer.substack.com/p/post'})
    db.complete_task(task,BROKEN,'original','','local')
    version=db.get_versions(task)[0]
    assert (await client.get(f'/api/video-notes/tasks/{task}?view=note')).json()['markdown']==FIXED
    assert (await client.get(f'/api/video-notes/tasks/{task}')).json()['versions'][0]['content']==FIXED
    assert (await client.get(f'/api/video-notes/tasks/{task}/versions/{version["id"]}')).json()['content']==FIXED
    assert db._backend.get_task(task,'local')['markdown']==BROKEN
    assert db.get_version(task,version['id'])['content']==BROKEN
