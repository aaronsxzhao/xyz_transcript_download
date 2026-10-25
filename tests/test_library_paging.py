from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from api.auth import User, get_current_user
from api.routers import library


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, fields): self.fields = fields.split(','); return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r[key] == value]; return self
    def in_(self,key,values): self.rows=[r for r in self.rows if r[key] in values]; return self
    def ilike(self, key, value):
        text = value.strip('%').casefold()
        self.rows = [r for r in self.rows if text in r[key].casefold()]; return self
    def lt(self, key, value): self.rows = [r for r in self.rows if r[key] < value]; return self
    def gt(self, key, value): self.rows = [r for r in self.rows if r[key] > value]; return self
    def order(self, key, desc): self.rows.sort(key=lambda r:r[key], reverse=desc); return self
    def limit(self, count):
        assert count <= 61
        self.rows = self.rows[:count]; return self
    def execute(self): return SimpleNamespace(data=[{k:r[k] for k in self.fields} for r in self.rows])


@pytest.mark.asyncio
async def test_source_catalog_skips_large_duplicate_groups_and_is_account_scoped(monkeypatch):
    rows = [dict(user_id='a', kind='video', source='A large channel', status='completed', markdown='Private body') for _ in range(2000)]
    rows += [dict(user_id='a', kind='podcast', source='B older podcast', status='completed'),
             dict(user_id='a', kind='video', source='C last channel', status='completed'),
             dict(user_id='a', kind='video', source='Failed import', status='failed'),
             dict(user_id='b', kind='video', source='Other account', status='completed'),
             dict(user_id='a', kind='video', source='', status='completed')]
    reads = []
    def table(_):
        query = Query(rows); reads.append(query); return query
    monkeypatch.setattr(library, 'get_db', lambda _: SimpleNamespace(use_supabase=True, db=SimpleNamespace(client=SimpleNamespace(table=table))))
    app = FastAPI(); app.include_router(library.router, prefix='/library')
    app.dependency_overrides[get_current_user] = lambda: User('a', '')
    async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as http:
        first = (await http.get('/library/sources')).json()
        assert first == {'sources': ['A large channel'], 'next_cursor': 'A large channel'}
        second = (await http.get('/library/sources', params={'cursor': first['next_cursor']})).json()
        assert second == {'sources': ['B older podcast', 'C last channel'], 'next_cursor': None}
        assert len(reads) == 2
        assert all(query.fields == ['source'] and len(query.rows) <= 41 for query in reads)
        podcasts = (await http.get('/library/sources', params={'kind': 'podcast'})).json()
        assert podcasts == {'sources': ['B older podcast'], 'next_cursor': None}
        assert (await http.get('/library/sources', params={'limit': 10000})).status_code == 422


@pytest.mark.asyncio
async def test_selected_source_is_exact_rather_than_a_substring(monkeypatch):
    rows = [dict(user_id='a', id=str(i), kind='video', title='Lesson', source=source,
                 date='2026-01-01', status='completed', search_text='Lesson', sort_key=str(i),
                 thumbnail='', platform='youtube', duration=60, topics_count=0,
                 published_at='', publication_sort_key=str(i))
            for i, source in enumerate(['Course', 'Course extra', '100%_Course'])]
    monkeypatch.setattr(library, 'get_db', lambda _: SimpleNamespace(use_supabase=True, db=SimpleNamespace(client=SimpleNamespace(table=lambda _: Query(rows)))))
    app = FastAPI(); app.include_router(library.router, prefix='/library')
    app.dependency_overrides[get_current_user] = lambda: User('a', '')
    async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as http:
        assert [r['source'] for r in (await http.get('/library', params={'source': 'Course'})).json()['items']] == ['Course']
        assert [r['source'] for r in (await http.get('/library', params={'source': '100%_Course'})).json()['items']] == ['100%_Course']


@pytest.mark.asyncio
async def test_cursor_traverses_large_library_with_tied_dates_and_account_isolation(monkeypatch):
    rows = [dict(user_id='a', id=str(i), kind='podcast' if i%2 else 'video', title=f'Lesson {i}', source='Source', date='2026-01-01', status='completed', search_text=f'Lesson {i} Source', sort_key=f'20260101:{i:05}', published_at='2024-01-01',publication_sort_key=f'20240101:{i:05}',thumbnail='https://image.xyzcdn.net/fixture.jpg', platform='xiaoyuzhou', duration=600, topics_count=4, markdown='Private full body') for i in range(2105)]
    rows.append({**rows[0], 'status':'failed', 'id':'failed-note', 'sort_key':'99999998'})
    rows.append({**rows[0], 'status':'pending', 'id':'pending-note', 'sort_key':'99999997'})
    rows.append({**rows[0], 'user_id':'b', 'id':'private-other', 'sort_key':'99999999'})
    client = SimpleNamespace(table=lambda _: Query(rows))
    monkeypatch.setattr(library, 'get_db', lambda _: SimpleNamespace(use_supabase=True,db=SimpleNamespace(client=client)))
    app=FastAPI(); app.include_router(library.router,prefix='/library')
    app.dependency_overrides[get_current_user]=lambda:User('a','')
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as http:
        ids=[]; cursor=''
        while True:
            response=await http.get('/library',params={'cursor':cursor,'limit':40})
            assert response.status_code==200
            page=response.json()
            assert len(page['items'])<=40
            assert all('markdown' not in r and 'user_id' not in r for r in page['items'])
            ids += [r['id'] for r in page['items']]
            cursor=page['next_cursor']
            if not cursor: break
        references=(await http.get('/library',params={'ids':'podcast:1,video:2,podcast:failed-note,podcast:private-other'})).json()['items']
        assert {r['id'] for r in references}=={'1','2'}
        assert (await http.get('/library',params={'ids':'video:1'})).json()['items']==[]
        assert (await http.get('/library',params={'ids':','.join('podcast:'+str(i) for i in range(31))})).status_code==422
        assert len(ids)==len(set(ids))==2105
        assert (await http.get('/library',params={'status':'failed'})).json()=={'items':[],'next_cursor':None}
        assert page['items'][0]['thumbnail'].startswith('https://')
        assert ids==[str(i) for i in reversed(range(2105))]
        oldest=(await http.get('/library',params={'sort':'oldest','kind':'podcast','q':'Lesson 1','source':'Source'})).json()['items']
        assert oldest[0]['id']=='1'
        assert all(int(r['id'])%2==1 and 'Lesson 1' in r['title'] for r in oldest)
        assert (await http.get('/library',params={'limit':10000})).status_code==422
        assert (await http.get('/library',params={'q':'no match'})).json()=={'items':[],'next_cursor':None}

@pytest.mark.asyncio
async def test_publication_order_has_its_own_stable_cursor_and_one_read(monkeypatch):
    rows=[];reads=[]
    for i in range(3):
        rows.append(dict(user_id='a',id=str(i),kind='video',title='Lesson',source='Source',date=f'2026-01-0{i+1}',status='completed',sort_key=f'2026010{i+1}',search_text='Lesson',thumbnail='',platform='youtube',duration=60,topics_count=0,published_at=f'2024-01-0{3-i}',publication_sort_key=f'2024010{3-i}:video:{i}'))
    def table(name):reads.append(name);return Query(rows)
    monkeypatch.setattr(library,'get_db',lambda _:SimpleNamespace(use_supabase=True,db=SimpleNamespace(client=SimpleNamespace(table=table))))
    app=FastAPI();app.include_router(library.router,prefix='/library');app.dependency_overrides[get_current_user]=lambda:User('a','')
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as http:
        first=(await http.get('/library',params={'sort':'published','limit':1})).json()
        assert first['items'][0]['id']=='0'
        assert first['next_cursor']=='20240103:video:0'
        assert reads==['library_items']
        second=(await http.get('/library',params={'sort':'published','limit':1,'cursor':first['next_cursor']})).json()
        assert second['items'][0]['id']=='1'
        saved=(await http.get('/library',params={'limit':1})).json()
        assert saved['items'][0]['id']=='2'
