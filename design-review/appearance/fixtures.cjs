const {chromium}=require('playwright'),fs=require('fs');
const root=__dirname;
const imgs={post:'post',home:'home',about:'about'};
const items=[
{id:'v1',kind:'video',content_type:'video',title:'在更大的世界里，重新理解人类的尺度',source:'远见之间',thumbnail:'https://review.invalid/post.jpg',status:'completed',date:'2026-10-29T01:30:00Z',published_at:'2026-10-28',platform:'youtube',duration:3360,topics_count:5},
{id:'p1',kind:'podcast',title:'我们为什么需要，一点无用的时间',source:'不止读书',thumbnail:'https://review.invalid/home.jpg',status:'completed',date:'2026-10-28T01:30:00Z',published_at:'2026-10-27',platform:'xiaoyuzhou',duration:2800,topics_count:4},
{id:'p2',kind:'podcast',title:'AI 时代，真正稀缺的能力是什么？',source:'硅谷 101',thumbnail:'',status:'completed',date:'2026-10-27T01:30:00Z',platform:'spotify',duration:4200,topics_count:6},
{id:'v2',kind:'video',content_type:'article',title:'走出去，才知道生活不止一种尺度',source:'慢慢来',thumbnail:'https://review.invalid/about.jpg',status:'completed',date:'2026-10-26T01:30:00Z',platform:'web',topics_count:3},
{id:'v3',kind:'video',title:'好的设计，应该让人忘记设计',source:'设计现场',thumbnail:'',status:'completed',date:'2026-10-25T01:30:00Z',platform:'bilibili',topics_count:4}
];
const markdown=`# 在更大的世界里，重新理解人类的尺度\n\n技术拓展了人的能力，也让选择变得更重要。我们如何在追求效率的同时，保留提问、判断，以及理解世界的耐心？\n\n## 探索的意义，不止是抵达\n\n当我们谈论探索，通常会想到距离：更远的星球，更深的海洋，或者还没有被命名的技术边界。但这场对话提出了另一个角度——探索同样改变着出发的人。\n\n站在地面上，我们习惯用眼前的尺度衡量事情。一旦视角被拉远，那些看似重要的区别会变得细小；而空气、水、彼此之间的联系，这些常被忽视的事，反而显得具体。\n\n> 真正改变我们的，有时不是获得了新的答案，而是终于能提出一个不同的问题。\n\n## 当工具越来越快，判断需要慢下来\n\n我们拥有了更快获取信息、更快生成答案的方式。但“做得更快”与“值得去做”之间，仍然隔着一个无法省略的判断。\n\n对日常工作而言，这意味着在行动之前多留一个停顿：我们试图解决什么？这个问题是谁提出的？如果答案很容易得到，问题本身是否还值得重新想一遍？\n\n## 留给自己的问题\n\n把注意力从“我还能做多少”，转向“我愿意认真对待什么”。一个好的想法，不一定立刻改变生活。但如果它让我们在下一次选择时多想了几秒，阅读就已经发生了作用。`;
const video={id:'v1',url:'https://example.com/video',platform:'youtube',title:items[0].title,thumbnail:items[0].thumbnail,channel:items[0].source,channel_url:'',channel_avatar:'',status:'success',progress:100,message:'',markdown,transcript:{text:'示例逐字稿。探索也改变着出发的人。',segments:[{start:0,end:12,text:'探索也改变着出发的人。'}],duration:3360},style:'detailed',model:'example',formats:[],quality:'',extras:'',video_understanding:false,video_interval:0,grid_cols:0,grid_rows:0,duration:3360,error:'',published_at:'2026-10-28',created_at:'2026-10-29T01:00:00Z',updated_at:'2026-10-29T01:30:00Z',versions:[]};
const summary={episode_id:'p1',title:items[1].title,overview:'散步、发呆、读一本没有目的的书。当生活的每一分钟都被安排好，那些不产生结果的时刻，反而可能最重要。',key_points:[{topic:'不是所有时间，都需要有用',summary:'散步的时候，我们不一定要听一期播客。读书的时候，也不一定需要记住一个结论。那些不急着产生结果的时刻，是生活得以展开的空间。',original_quote:'把一段时间还给自己，不需要先证明它的价值。',timestamp:'08:24'},{topic:'给注意力一点空白',summary:'留一点空白，可能只是走一条不同的路，或者在一个下午读几页没有目的的书。没有步骤，也不必成为新的任务。',original_quote:'安排得很满，并不总意味着过得充实。',timestamp:'16:42'}],topics:['不是所有时间，都需要有用','给注意力一点空白'],takeaways:['今天留出十分钟，不播放、不记录，也不试图完成什么。']};

const podcasts=[{pid:'pod1',title:'不止读书',author:'不止读书',description:'在阅读和生活之间，留一点思考的空间。',cover_url:'https://review.invalid/home.jpg',episode_count:24,summarized_count:18,platform:'xiaoyuzhou',feed_url:''}];
const episodes=[{eid:'p1',pid:'pod1',title:items[1].title,description:'关于时间、注意力与生活的一次对话。',duration:2800,pub_date:'2026-10-27',cover_url:podcasts[0].cover_url,audio_url:'',status:'completed',has_transcript:true,has_summary:true,topics_count:4,key_points_count:6,created_at:'2026-10-27'}];
const channels=[{channel:'远见之间',platform:'youtube',channel_url:'https://example.com/channel',channel_avatar:'',thumbnail:items[0].thumbnail,total:12,done:10,last_updated:'2026-10-29'}];
const settings={whisper_mode:'api',whisper_model:'whisper-large-v3',whisper_backend:'api',whisper_device:'cpu',llm_model:'gpt-5',llm_provider:'server',transcription_provider:'server',llm_base_url:'',whisper_base_url:'',llm_key_saved:false,whisper_key_saved:false,groq_available:false,llm_configured:true,whisper_provider:'server',check_interval:60};
async function fixtures(c,auth=false){await c.route('**/api/**',async route=>{const u=new URL(route.request().url()); let data={};
if(u.pathname.includes('image-proxy')){const name=(u.searchParams.get('url')||'post.jpg').split('/').pop().replace('.jpg','');return route.fulfill({contentType:'image/jpeg',body:fs.readFileSync(`${root}/fixtures/${imgs[name]||'post'}.jpg`)})}
if(u.pathname==='/api/auth/config')data={supabase_enabled:auth,supabase_url:null};
else if(u.pathname==='/api/stats')data={total_podcasts:12,total_episodes:48,total_transcripts:48,total_summaries:42,total_video_channels:8,total_videos:80,completed_videos:74};
else if(u.pathname==='/api/library/sources')data={sources:items.map(i=>i.source),next_cursor:null};
else if(u.pathname==='/api/library')data={items,next_cursor:null};
else if(u.pathname==='/api/content-updates')data={items:[]};
else if(u.pathname.includes('/video-notes/tasks/v1'))data=video;
else if(u.pathname==='/api/video-notes/channels')data={channels};
else if(u.pathname==='/api/video-notes/tasks/by-channel')data={tasks:[video],next_cursor:null};
else if(u.pathname==='/api/summaries/p1')data=summary;
else if(u.pathname.includes('transcript'))data={episode_id:'p1',text:'示例原文',segments:[{start:0,end:12,text:'把一段时间还给自己，不需要先证明它的价值。'}],duration:2800};
else if(u.pathname==='/api/episodes/p1')data=episodes[0];
else if(u.pathname==='/api/podcasts/content')data=episodes;
else if(u.pathname==='/api/podcasts')data=podcasts;
else if(u.pathname==='/api/settings')data=settings;
else if(u.pathname==='/api/cookies')data={cookies:[]};
else if(u.pathname.includes('video'))data={tasks:[],channels:[]};
else if(u.pathname.includes('jobs'))data=[];
else if(u.pathname.includes('summaries'))data=[];
else if(u.pathname.includes('health'))data={status:'ok'};
return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
})}
module.exports={fixtures};
