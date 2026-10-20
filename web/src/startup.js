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
  document.getElementById('startup-retry')?.addEventListener('click', () => location.reload());
  const recoverEntry = () => {
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
    else if (path === '/library') urls = ['/api/summaries', '/api/video-notes/tasks'];
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
