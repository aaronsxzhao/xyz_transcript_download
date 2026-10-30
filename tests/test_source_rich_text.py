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


def test_existing_original_repair_adds_version_without_changing_prose(tmp_path):
    from video_task_db import VideoTaskDB
    from social_content import SocialContent
    from scripts.repair_article_formatting import repair_one
    db=VideoTaskDB(tmp_path/'articles.sqlite')
    ident=db.create_task({'url':'https://x.com/i/status/123','platform':'twitter','user_id':'owner','style':'original'})
    old=SocialContent('twitter','https://x.com/i/status/123','Title','Important fact.')
    new=SocialContent('twitter',old.url,old.title,'**Important** fact.')
    db.complete_task(ident,old.markdown(),'original','','owner')
    before=db.get_versions(ident)[0]['content']
    assert repair_one(db,db.get_task(ident,'owner'),lambda _:new)=='repaired'
    assert len(db.get_versions(ident))==2
    assert any(version['content']==before for version in db.get_versions(ident))


def test_changed_or_unavailable_original_does_not_replace_saved_article(tmp_path):
    from video_task_db import VideoTaskDB
    from social_content import SocialContent,SocialSourceError
    from scripts.repair_article_formatting import repair_one
    db=VideoTaskDB(tmp_path/'articles.sqlite')
    ident=db.create_task({'url':'https://x.com/i/status/123','platform':'twitter','user_id':'owner','style':'original'})
    old=SocialContent('twitter','https://x.com/i/status/123','Title','Old fact.')
    new=SocialContent('twitter',old.url,old.title,'**Different** fact.')
    db.complete_task(ident,old.markdown(),'original','','owner')
    task=db.get_task(ident,'owner')
    assert repair_one(db,task,lambda _:new)=='changed_source_kept'
    def unavailable(_):raise SocialSourceError('Source access unavailable')
    assert repair_one(db,task,unavailable)=='source_unavailable'
    assert len(db.get_versions(ident))==1
    assert db.get_task(ident,'owner')['markdown']==old.markdown()


def test_format_repair_does_not_change_code_whitespace_or_link_destinations(tmp_path):
    from video_task_db import VideoTaskDB
    from social_content import SocialContent
    from scripts.repair_article_formatting import repair_one
    db=VideoTaskDB(tmp_path/'articles.sqlite')
    ident=db.create_task({'url':'https://x.com/i/status/123','platform':'twitter','user_id':'owner','style':'original'})
    old=SocialContent('twitter','https://x.com/i/status/123','Title','Fact [reference](https://example.com/old).\n\n```python\n  work()\n```')
    db.complete_task(ident,old.markdown(),'original','','owner')
    for body in ['**Fact** [reference](https://example.com/new).\n\n```python\n  work()\n```','**Fact** [reference](https://example.com/old).\n\n```python\nwork()\n```']:
        source=SocialContent('twitter',old.url,old.title,body)
        assert repair_one(db,db.get_task(ident,'owner'),lambda _:source)=='changed_source_kept'
    assert len(db.get_versions(ident))==1

@pytest.mark.parametrize('literal', ['2018. College bedroom.', '42) A literal label.', '- Not a source list', '+ Not a source list', '# Not a source heading', '## Not a source heading', '---', '==='])
def test_literal_paragraph_block_markers_do_not_change_source_structure(literal):
    from source_rich_text import escape_text
    html=rendered(escape_text(literal))
    assert html.strip()==f'<p>{literal}</p>'


def test_split_year_and_punctuation_remain_a_paragraph_in_html_and_json():
    html='<p><span>2018</span><span>. College bedroom.</span></p>'
    body={'type':'paragraph','content':[{'type':'text','text':'2018'},{'type':'text','text':'. College bedroom.'}]}
    assert rendered(html_markdown(html,'https://example.com')).strip()=='<p>2018. College bedroom.</p>'
    assert rendered(_body_json(body)).strip()=='<p>2018. College bedroom.</p>'


def test_real_source_lists_and_code_keep_their_semantics():
    result=rendered(html_markdown('<ol start="2018"><li><p>First</p></li><li>Second</li></ol><pre>2018. Code</pre>','https://example.com'))
    assert '<ol start="2018">' in result
    assert '<li>' in result and 'Second</li>' in result
    assert '<code>2018. Code\n</code>' in result
    body={'type':'ordered_list','attrs':{'order':2018},'content':[{'type':'list_item','content':[{'type':'paragraph','content':[{'type':'text','text':'First'}]}]}]}
    assert '<ol start="2018">' in rendered(_body_json(body))


def test_large_ordered_source_list_keeps_continuation_paragraphs_inside_item():
    result=rendered(html_markdown('<ol start="2018"><li><p>First paragraph.</p><p>Second paragraph.</p><ul><li>Nested item.</li></ul></li></ol>','https://example.com'))
    from bs4 import BeautifulSoup
    tree=BeautifulSoup(result,'html.parser')
    assert tree.ol['start']=='2018'
    assert len(tree.ol.li.find_all('p',recursive=False))==2
    assert tree.ol.li.ul.li.get_text(strip=True)=='Nested item.'


def test_json_code_block_does_not_escape_a_year_or_list_example():
    body={'type':'code_block','content':[{'type':'text','text':'2018. example\n- literal'}]}
    assert '<code>2018. example\n- literal\n</code>' in rendered(_body_json(body))
