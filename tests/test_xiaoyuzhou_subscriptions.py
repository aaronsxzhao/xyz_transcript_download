"""Public profile metadata must never be mistaken for a subscription list."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from xyz_client import XyzClient, SubscriptionSourceError

UID='0123456789abcdef01234567'
PID='abcdef0123456789abcdef01'


def source(props=None, html='', error=None):
    client=XyzClient.__new__(XyzClient)
    content=('<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':props or {}}})+'</script>'+html).encode()
    client.session=SimpleNamespace(get=Mock(return_value=SimpleNamespace(content=content,raise_for_status=lambda:None),side_effect=error))
    return client


@pytest.mark.parametrize('value',[UID,UID.upper(),'https://www.xiaoyuzhoufm.com/user/'+UID+'?source=share','xiaoyuzhoufm.com/user/'+UID,'我的主页 https://www.xiaoyuzhoufm.com/user/'+UID+' 看看'])
def test_actual_id_and_shared_profile_link(value):
    assert source().extract_user_id(value)==UID


@pytest.mark.parametrize('value',['昵称','nickname','https://evil.example/user/'+UID,'https://notxiaoyuzhoufm.com/user/'+UID,'https://www.xiaoyuzhoufm.com/podcast/'+PID,'https://www.xiaoyuzhoufm.com/user/'+UID+'extra'])
def test_nicknames_and_other_urls_are_not_user_ids(value):
    assert source().extract_user_id(value) is None


def test_current_public_profile_with_visible_count_is_not_an_empty_or_owned_subscription_list():
    client=source({'profile':{'user':{'uid':UID},'userStats':{'realSubscriptionCount':495,'subscriptionCountForViewer':492},'ownedPodcasts':[{'pid':PID,'title':'Owned show'}],'recentPlayedEpisodes':[]}},html=f'<a href="/podcast/{PID}">Owned or recommended show</a>')
    with pytest.raises(SubscriptionSourceError,match='does not expose') as error:
        client.get_user_subscriptions(UID)
    assert error.value.status_code==422


@pytest.mark.parametrize('wrap',[lambda s:{'subscriptions':s},lambda s:{'subscribedPodcasts':s},lambda s:{'profile':{'subscriptions':s}},lambda s:{'user':{'subscriptions':s}}])
def test_only_explicit_subscriptions_are_imported_and_deduplicated(wrap):
    entry={'podcast':{'pid':PID,'title':'Synthetic show','brief':'隐私 is a topic, not a privacy flag'}}
    result=source(wrap([entry,entry])).get_user_subscriptions(UID)
    assert [p.pid for p in result]==[PID]
    assert result[0].description.startswith('隐私')


def test_explicit_empty_list_remains_distinct_from_missing_data():
    assert source({'subscriptions':[]}).get_user_subscriptions(UID)==[]


@pytest.mark.parametrize('status,expected',[(404,404),(403,403),(429,429),(500,503),(502,503)])
def test_upstream_failure_is_not_reported_as_private_or_empty(status,expected):
    response=requests.Response();response.status_code=status
    client=source(error=requests.HTTPError('private upstream response',response=response))
    with pytest.raises(SubscriptionSourceError) as error:client.get_user_subscriptions(UID)
    assert error.value.status_code==expected
    assert 'private upstream' not in str(error.value)


def test_network_failure_is_safe_and_retryable():
    with pytest.raises(SubscriptionSourceError) as error:
        source(error=requests.Timeout('private endpoint')).get_user_subscriptions(UID)
    assert error.value.status_code==503 and 'private endpoint' not in str(error.value)


@pytest.mark.asyncio
async def test_unavailable_list_cannot_save_owned_podcasts(client,monkeypatch):
    from api.routers import podcasts
    upstream=source({'profile':{'ownedPodcasts':[{'pid':PID,'title':'Owned'}]}})
    monkeypatch.setattr('xyz_client.get_client',lambda:upstream)
    database=Mock();monkeypatch.setattr(podcasts,'get_db',lambda _:database)
    response=await client.post('/api/podcasts/import-subscriptions',json={'username':UID})
    assert response.status_code==422 and 'does not expose' in response.json()['detail']
    database.add_podcast.assert_not_called();database.add_episode.assert_not_called()
