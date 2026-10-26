"""Verify source styling survives import, rendering and Markdown/Notion export."""
import pytest
from markdown_it import MarkdownIt
from social_content import _twitter_article_body,html_markdown,_body_json
from source_rich_text import draft_inline


def rendered(markdown):return MarkdownIt().render(markdown)


def test_twitter_bold_italic_strike_and_utf16_links_survive_import():
    raw='😀 bold italic link'
    article={'content':{'blocks':[{'text':raw,'inlineStyleRanges':[
        {'offset':3,'length':4,'style':'BOLD'},{'offset':8,'length':6,'style':'ITALIC'}],
        'entityRanges':[{'offset':15,'length':4,'key':0}]}],
        'entityMap':{'0':{'type':'LINK','data':{'url':'https://example.com/evidence'}}}}}
    body,_=_twitter_article_body(article,'https://x.com/i/status/123')
    html=rendered(body)
    assert '<strong>bold</strong>' in html
    assert '<em>italic</em>' in html
    assert '<a href="https://example.com/evidence">link</a>' in html
    assert html.startswith('<p>😀 ')


@pytest.mark.parametrize('first,second',['BOLD ITALIC'.split(),'ITALIC BOLD'.split()])
def test_crossing_ranges_do_not_print_delimiters_or_lose_original_characters(first,second):
    result=draft_inline('abcdefghi',[{'offset':0,'length':6,'style':first},{'offset':3,'length':6,'style':second}])
    html=rendered(result)
    from bs4 import BeautifulSoup
    assert BeautifulSoup(html,'html.parser').get_text().strip()=='abcdefghi'
    assert '<strong>' in html and '<em>' in html


def test_invalid_surrogate_ranges_cannot_drop_emoji_or_source_words():
    assert draft_inline('😀 keep', [{'offset':1,'length':2,'style':'BOLD'}])=='😀 keep'


def test_styled_text_around_atomic_media_retains_order_and_marks():
    article={'content':{'blocks':[{'text':'Bold X after','inlineStyleRanges':[{'offset':0,'length':4,'style':'BOLD'},{'offset':7,'length':5,'style':'ITALIC'}],
        'entityRanges':[{'offset':5,'length':1,'key':0}]}],
        'entityMap':{'0':{'type':'MEDIA','data':{'mediaItems':[{'mediaId':'image'}]}}}},
        'media_entities':[{'media_id':'image','media_info':{'original_img_url':'https://pbs.twimg.com/evidence.jpg'}}]}
    body,_=_twitter_article_body(article,'https://x.com/i/status/123')
    assert body.index('**Bold**')<body.index('evidence.jpg')<body.index('*after*')


@pytest.mark.parametrize('html',[
 '<p>Before <strong> important </strong> after.</p>',
 '<p>Before <span style="font-weight:700">important</span> after.</p>',
 '<p>Before <b>important</b> after.</p>',
])
def test_html_semantic_or_inline_css_bold_renders_as_bold(html):
    result=rendered(html_markdown(html,'https://example.com'))
    assert '<strong>important</strong>' in result
    assert 'Before ' in result and ' after.' in result


def test_chinese_punctuation_does_not_leave_literal_stars():
    assert '<strong>重要</strong>，下文' in rendered(html_markdown('<p><strong>重要，</strong>下文</p>','https://example.com'))


def test_html_italic_strike_and_source_code_are_not_interpreted_as_prose():
    result=html_markdown('<p><span style="font-style:italic">source</span> <del>old</del> <code>a*b_`x`</code></p>','https://example.com')
    assert '<em>source</em>' in rendered(result)
    assert '~~old~~' in result
    assert '<code>a*b_`x`</code>' in rendered(result)


def test_draft_code_keeps_literal_backticks_and_spaces():
    value='some `code`'
    assert '<code>`code`</code>' in rendered(draft_inline(value,[{'offset':5,'length':6,'style':'CODE'}]))


def test_substack_json_code_and_bad_heading_metadata_still_deliver_source():
    assert '<code>a*b_`x`</code>' in rendered(_body_json({'type':'text','text':'a*b_`x`','marks':[{'type':'code'}]}))
    assert '## Original' in _body_json({'type':'heading','attrs':{'level':'bad'},'content':[{'type':'text','text':'Original'}]})


def test_markdown_export_retains_notion_rich_text_annotations():
    from notion_markdown import to_notion
    markdown,_=_twitter_article_body({'content':{'blocks':[{'text':'Important fact','inlineStyleRanges':[{'offset':0,'length':9,'style':'BOLD'}]}]}},'https://x.com/i/status/123')
    blocks=to_notion(markdown)
    text=blocks[0]['paragraph']['rich_text']
    assert any(item.get('annotations',{}).get('bold') and item['text']['content']=='Important' for item in text)


def test_literal_markdown_characters_inside_bold_do_not_escape_the_wrapper():
    result=rendered(html_markdown('<p><strong>*literal*</strong></p>','https://example.com'))
    assert '<strong>*literal*</strong>' in result


def test_whitespace_only_code_does_not_gain_padding():
    from source_rich_text import inline_code
    assert '<code>   </code>' in rendered(inline_code('   '))


def test_adjacent_equivalent_html_marks_are_not_literal_asterisk_runs():
    for html in ['<p><strong>A</strong><b>B</b></p>','<p><span style="font-weight:700">A</span><span style="font-weight:700">B</span></p>']:
        assert '<strong>AB</strong>' in rendered(html_markdown(html,'https://example.com'))


def test_source_soft_line_breaks_inside_draft_paragraph_remain_visible():
    assert '<br />' in rendered(draft_inline('First line\nSecond line'))
