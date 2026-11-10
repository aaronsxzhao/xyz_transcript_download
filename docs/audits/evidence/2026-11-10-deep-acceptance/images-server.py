import os,sys,json,io
from pathlib import Path
sys.path.insert(0,'/workspace/deep-acceptance')
R=Path('/workspace/deep-acceptance-private/images-data');R.mkdir(exist_ok=True)
os.environ.update(XYZ_DATA_DIR=str(R),SUPABASE_URL='',SUPABASE_KEY='',SUPABASE_ANON_KEY='',SUPABASE_SERVICE_ROLE_KEY='')
import config
assert not config.USE_SUPABASE
from PIL import Image,ImageDraw
from content_sources import extract_public_article
html='<html><head><title>Controlled image acceptance</title></head><body><nav>OUTER_NAV_SENTINEL</nav><article><h1>Controlled image acceptance</h1><div class="site-links">INNER_NAV_SENTINEL <a href="https://example.com/menu">Menu</a></div>'
for i in range(24):html+=f'<h2>Section {i+1}</h2><p>'+('Controlled synthetic prose for full article scrolling and image testing. '*12)+f'</p><img src="https://fixture.example/image-{i}.png?current-build=1" alt="Chart {i+1}">'
html+='</article></body></html>'
(R/'source.html').write_text(html)
doc=extract_public_article(html.encode(),'https://fixture.example/article')
from video_task_db import get_video_task_db
db=get_video_task_db()
if not db.get_task('audit-images',user_id='local'):db.create_task({'id':'audit-images','url':'https://fixture.example/article','platform':'web','title':doc.title,'status':'success','style':'original','formats':['original'],'user_id':'local'})
db.update_task('audit-images',{'markdown':doc.markdown(),'progress':100})
from api import article_images
from public_content_fetch import PublicResponse
from social_content import SocialSourceError
original=article_images.fetch_public
calls={}
def fixture(url,*args,**kw):
 if not url.startswith('https://fixture.example/image-'):return original(url,*args,**kw)
 i=int(url.split('image-')[1].split('.')[0]);calls[i]=calls.get(i,0)+1
 if i==23 and not (R/'release-image').exists():raise SocialSourceError('Controlled image origin failure')
 w,h=(1200,800) if i%2==0 else (600,1200)
 im=Image.new('RGB',(w,h),'#e8dfc4');d=ImageDraw.Draw(im);d.rectangle((8,8,w-9,h-9),outline='#004477',width=8);d.line((0,0,w,h),fill='#b04828',width=8);d.line((w,0,0,h),fill='#b04828',width=8);d.text((30,30),'Controlled chart '+str(i+1),fill='black');b=io.BytesIO();im.save(b,format='PNG')
 return PublicResponse(url,'image/png',b.getvalue(),{})
article_images.fetch_public=fixture
from api.main import app
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=18792,log_level='error')
