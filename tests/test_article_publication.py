import json
import time
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from article_publication import publication_name, substack_publication
from content_sources import extract_public_article
from social_content import SocialContent, SocialSourceError


def test_generic_blog_keeps_publication_and_author_separate_without_changing_body():
    raw=b'<html><head><meta property="og:site_name" content="Example Blog"><meta name="author" content="Alice"></head><body><article><h1>Title</h1><p>Original words.</p></article></body></html>'
    source=extract_public_article(raw,'https://example.com/post')
    assert source.publication=='Example Blog' and source.author=='Alice'
    assert source.metadata()['publication']=='Example Blog'
    assert source.metadata()['author']=='Alice'
    assert 'Author: Alice' in source.markdown() and 'Original words.' in source.body


def test_website_without_named_author_does_not_invent_one_from_its_domain():
    raw=b'<meta property="og:site_name" content="Example Blog"><article><h1>Title</h1><p>Original words.</p></article>'
    source=extract_public_article(raw,'https://example.com/post')
    assert source.metadata()['publication']=='Example Blog'
    assert source.metadata()['author']==''
    assert 'Source: example.com' in source.markdown()


@pytest.mark.parametrize('record', [{'publisher':{'name':'Named Blog'}},{'isPartOf':{'name':'Named Blog'}}])
def test_structured_publication_is_used_without_title_guessing(record):
    soup=BeautifulSoup('<title>An article - guessed suffix</title>','html.parser')
    assert publication_name(soup,record)=='Named Blog'
    assert publication_name(soup)==''


def test_substack_envelope_avoids_an_extra_network_request(monkeypatch):
    read=Mock(side_effect=AssertionError('No extra request'))
    monkeypatch.setattr('social_content._read',read)
    assert substack_publication({'publication':{'id':7,'name':'Named Blog'}},{'publication_id':7},'https://example.com/p/post',time.monotonic()+30)=='Named Blog'
    read.assert_not_called()


@pytest.mark.parametrize('publication_id,expected', [(7,'Named Blog'),(8,'')])
def test_optional_substack_metadata_must_match_the_imported_publication(monkeypatch,publication_id,expected):
    html='<script id="preloads-json" type="application/json">'+json.dumps({'pub':{'id':publication_id,'name':'Named Blog'}})+'</script>'
    read=Mock(return_value=(html.encode(),'https://example.com/p/post'))
    monkeypatch.setattr('social_content._read',read)
    before=time.monotonic()
    assert substack_publication({}, {'publication_id':7},'https://example.com/p/post',before+30)==expected
    assert read.call_args.args[1] <= before+8.1


def test_optional_publication_failure_keeps_complete_article_import_available(monkeypatch):
    monkeypatch.setattr('social_content._read',Mock(side_effect=SocialSourceError('Unavailable')))
    assert substack_publication({}, {'publication_id':7},'https://example.com/p/post',time.monotonic()+30)==''


def test_import_uses_publication_in_existing_source_paths_and_keeps_it_on_metadata_outage(monkeypatch,tmp_path):
    from api.routers import video_notes as routes
    from video_task_db import VideoTaskDB
    from api.routers.library import _local_library_rows
    db=VideoTaskDB(tmp_path/'publication.db')
    url='https://writer.substack.com/p/article'
    ident=db.create_task({'id':'publication-test','url':url,'platform':'substack','user_id':'owner'})
    source=SocialContent('substack',url,'Title','Complete original source.','Alice',publication='Named Blog')
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr('social_content.resolve_social_content',lambda url:source)
    monkeypatch.setattr(routes,'_broadcast_from_thread',Mock())
    monkeypatch.setattr(routes,'start_task',Mock())
    model=Mock(side_effect=AssertionError('Original text needs no model'))
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings',model)
    for publication in ['Named Blog','']:
        source.publication=publication
        db.update_task(ident,{'status':'pending'})
        routes.process_video_note_sync(ident,url,'substack','detailed',['summary'],'medium','','',False,4,3,3,'owner')
        task=db.get_task(ident,'owner')
        assert task['status']=='success', task.get('message')
        assert task['channel']=='Named Blog'
        assert task['source_metadata']['publication']=='Named Blog'
        assert task['source_metadata']['author']=='Alice'
        assert 'Author: Alice' in task['markdown']
        assert 'Complete original source.' in task['markdown']
        library_db=Mock();library_db.get_all_summaries.return_value=[]
        assert _local_library_rows(library_db,'owner')[0]['source']=='Named Blog'
    model.assert_not_called()
