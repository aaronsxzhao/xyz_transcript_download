"""Read-only checks of this account's public covers; emit numeric aggregates only."""
import asyncio
from urllib.parse import urlencode
import httpx
from api.covers import validate_url
from api.supabase_client import get_supabase_admin_client


def profile_covers(owner):
    client=get_supabase_admin_client()
    if client is None:
        return []
    rows=client.table('library_items').select('thumbnail').eq('user_id',owner).eq('status','completed').limit(200).execute().data or []
    rows+=client.table('podcasts').select('cover_url').eq('user_id',owner).limit(100).execute().data or []
    urls=set()
    for row in rows:
        url=row.get('thumbnail') or row.get('cover_url') or ''
        try:validate_url(url)
        except Exception:continue
        urls.add(url)
    return [asyncio.run(measure(urls))]


async def measure(urls):
    report={'library_profile':'check_public_covers','status':200,'covers_checked':len(urls),'covers_loaded':0,'covers_failed':0,
            'cover_disk_hits':0,'cover_storage_hits':0,'cover_origin_hits':0,'upstream_403':0,'upstream_404':0}
    slots=asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=30) as client:
        async def check(url):
            async with slots:
                try:
                    response=await client.get('https://aipodcastsummary.online/api/image-proxy?'+urlencode({'url':url,'v':2}))
                    if response.status_code in {502,503,504}:
                        await asyncio.sleep(3.5)
                        response=await client.get('https://aipodcastsummary.online/api/image-proxy?'+urlencode({'url':url,'v':2}))
                    if response.status_code==200 and response.content.startswith(b'RIFF'):
                        report['covers_loaded']+=1
                        source=response.headers.get('x-artwork-cache','')
                        if source in {'disk','storage','origin'}:report['cover_'+source+'_hits']+=1
                    else:
                        report['covers_failed']+=1
                        status=response.headers.get('x-artwork-upstream-status')
                        if status in {'403','404'}:report['upstream_'+status]+=1
                except Exception:report['covers_failed']+=1
        try:await asyncio.wait_for(asyncio.gather(*(check(url) for url in urls)),timeout=90)
        except asyncio.TimeoutError:pass
    report['covers_failed']=report['covers_checked']-report['covers_loaded']
    if report['covers_failed']:report['status']=500
    return report
