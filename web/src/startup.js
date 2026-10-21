/* Runs before framework downloads. Public shell only; APIs still verify tokens. */
(() => {
  const titles = { '/': 'Dashboard', '/library': 'Library', '/podcasts': 'Podcasts', '/videos': 'Videos', '/settings': 'Settings', '/login': 'Sign in', '/reset-password': 'Reset password' };
  const path = location.pathname;
  const title = titles[path] || (path.startsWith('/podcasts/') ? 'Episodes' : path.startsWith('/viewer/') ? 'Summary' : 'Video note');
  const heading = document.getElementById('startup-title');
  if (heading) heading.textContent = title;
  document.querySelectorAll('[data-startup-nav]').forEach(link => {
    if (link.pathname === path || (link.pathname !== '/' && path.startsWith(link.pathname + '/'))) link.setAttribute('aria-current', 'page');
  });
  let startupReported = false;
  let scriptErrors = 0;
  window.addEventListener('error', () => { if (document.getElementById('startup-shell')) scriptErrors++; }, true);
  const reportStartup = outcome => {
    if (startupReported || !document.getElementById('startup-shell')) return;
    try {
      const token = localStorage.getItem('xyz_access_token') || sessionStorage.getItem('xyz_access_token');
      if (!token) return;
      const page = path.startsWith('/podcasts/') ? 'episodes' : path.startsWith('/viewer/') ? 'viewer' : path.startsWith('/videos/') ? 'video_note' : path === '/videos' && new URLSearchParams(location.search).has('channel') ? 'channel' : ({'/':'dashboard','/library':'library','/podcasts':'podcasts','/videos':'videos','/settings':'settings'})[path];
      if (!page) return;
      startupReported = true;
      const bound = number => Math.max(0,Math.min(300000,Math.round(number || 0)));
      const modules = performance.getEntriesByType('resource').filter(entry => { const url = new URL(entry.name);return url.origin === location.origin && url.pathname.startsWith('/assets/') && url.pathname.endsWith('.js'); });
      // Numbers/fixed labels only. Never send URLs, source text or error text.
      void fetch('/api/performance',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({page,stage:'bootstrap',outcome,elapsed_ms:bound(performance.now()),first_paint_ms:bound(performance.getEntriesByName('first-contentful-paint')[0]?.startTime),document_ms:bound(performance.getEntriesByType('navigation')[0]?.responseEnd),api_ms:0,cached:!!navigator.serviceWorker?.controller,program_embedded:!!document.querySelector('[data-document-program]'),module_requests:modules.length,module_failures:modules.filter(entry=>entry.responseStatus >= 400).length,script_errors:Math.min(1000,scriptErrors)})}).catch(()=>{});
    } catch { /* Diagnostics never block startup, including restricted storage. */ }
  };
  document.getElementById('startup-retry')?.addEventListener('click', () => {
    const fresh = new URL(location.href);fresh.searchParams.set('__xyz_boot',String(Date.now()));location.replace(fresh.href);
  });
  const recoverEntry = () => {
    reportStartup('error');
    try {
      const previous = Number(sessionStorage.getItem('xyz:entry-recovery') || 0);
      if (Date.now() - previous > 60000) {
        sessionStorage.setItem('xyz:entry-recovery', String(Date.now()));
        const fresh = new URL(location.href); fresh.searchParams.set('__xyz_boot', String(Date.now()));
        location.replace(fresh.href); return;
      }
    } catch { /* Without storage, leave a manual retry instead of risking a reload loop. */ }
    const message = document.getElementById('startup-status');
    if (message) message.textContent = 'Some page files could not load. Please retry loading.';
    const retry = document.getElementById('startup-retry'); if (retry) retry.hidden = false;
  };
  window.addEventListener('xyz:entry-error', recoverEntry);
  if (window.__xyzEntryFailed) recoverEntry();
  setTimeout(() => {
    reportStartup('slow');
    const message = document.getElementById('startup-status');
    if (message) message.textContent = 'The connection is taking longer than expected. You can retry loading.';
    const retry = document.getElementById('startup-retry');
    if (retry) retry.hidden = false;
  }, 12000);
  try {
    const token = localStorage.getItem('xyz_access_token') || sessionStorage.getItem('xyz_access_token');
    if (!token) return;
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (!payload.exp || payload.exp <= Date.now() / 1000 + 30) return;
    const parts = path.split('/').filter(Boolean);
    const id = parts[1] && encodeURIComponent(decodeURIComponent(parts[1]));
    let urls = [];
    if (path === '/settings') urls = ['/api/settings'];
    else if (path === '/podcasts') urls = ['/api/podcasts'];
    else if (path === '/library') { const p = new URLSearchParams(location.search); urls = ['/api/library?' + new URLSearchParams({q:p.get('q')||'',kind:p.get('kind')||'',status:p.get('status')||'',source:p.get('source')||'',sort:p.get('sort')||'newest'})]; }
    else if (parts[0] === 'podcasts' && parts[2] === 'episodes') urls = [`/api/podcasts/${id}`, `/api/podcasts/${id}/episodes?offset=0&limit=50`];
    else if (parts[0] === 'viewer' && id) urls = [`/api/summaries/${id}`];
    else if (parts[0] === 'videos' && id) urls = [`/api/video-notes/tasks/${id}?view=note`];
    else if (path === '/videos') {
      const params = new URLSearchParams(location.search);
      urls = [params.has('channel') ? '/api/video-notes/tasks/by-channel?' + new URLSearchParams({platform:params.get('platform') || 'youtube',channel:params.get('channel') || ''}) : '/api/video-notes/channels'];
    } else if (path === '/') urls = ['/api/summaries/recent?limit=6', '/api/video-notes/recent?limit=6'];
    const reads = new Map();
    window.__xyzStartupReads = reads;
    for (const url of urls) {
      const key = new URL(url, location.origin); key.searchParams.sort();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const response = fetch(url, { headers:{Authorization:`Bearer ${token}`}, signal:controller.signal })
        .then(async result => ({body:await result.text(),status:result.status,headers:result.headers}))
        .catch(() => null).finally(() => clearTimeout(timeout));
      reads.set(key.pathname + key.search, {token,response});
    }
  } catch { /* Blocked storage or an expired session uses normal sign-in handling. */ }
})();
