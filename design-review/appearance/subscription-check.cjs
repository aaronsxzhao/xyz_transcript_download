const {chromium}=require('playwright'),{fixtures}=require('./fixtures.cjs'),fs=require('fs');
const out=__dirname;
(async()=>{const b=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});const results=[];
for(const design of ['classic','editorial'])for(const theme of ['dark','light'])for(const width of [1440,390,320]){
 const c=await b.newContext({viewport:{width,height:1000}});await fixtures(c);await c.addInitScript(({design,theme})=>{localStorage.setItem('xyz:design',design);localStorage.setItem('xyz:color-theme',theme)},{design,theme});const p=await c.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
 for(const [name,path] of [['subscription-list','/podcasts?platform=xiaoyuzhou'],['video-channels','/videos?platform=youtube'],['channel-videos','/videos?platform=youtube&channel='+encodeURIComponent('远见之间')],['video-add','/videos?add=local']]){
 await p.goto('http://localhost:5180'+path);await p.waitForTimeout(700);await p.locator('h1').first().waitFor();
 const record=async name=>{await p.waitForTimeout(250);const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth||[...document.querySelectorAll('.app-shell>main')].some(e=>e.scrollWidth>e.clientWidth));results.push({design,theme,width,name,overflow,errors:[...errors]});if(width!==320){const style=await p.addStyleTag({content:'.app-shell{height:auto;min-height:100vh}.app-shell>main{overflow:visible}'});await p.screenshot({path:`${out}/${design}-${theme}-${width}-${name}.png`,fullPage:true});await style.evaluate(e=>e.remove());}};
 await record(name);
 if(name==='settings'){for(const label of ['Platform Accounts','Tools & Data']){await p.getByRole('button',{name:label,exact:true}).click();await record(name+'-'+label.split(' ')[0].toLowerCase())}}
 }
 await c.close();
console.log(design,theme,width,'complete');
}
fs.writeFileSync(out+'/subscription-results.json',JSON.stringify(results,null,2));console.log('FAILURES',results.filter(r=>r.overflow||r.errors.length));await b.close()})().catch(e=>{console.error(e);process.exit(1)});
