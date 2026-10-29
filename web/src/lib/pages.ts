// Notes remain readable with the core styles if optional rich typography cannot load.
const pages = {
  resetPassword: () => import('../pages/ResetPassword'),
  library: () => import('../pages/Library'),
  dashboard: () => import('../pages/Dashboard'),
  podcasts: () => import('../pages/Podcasts'),
  episodes: () => import('../pages/Episodes'),
  viewer: () => Promise.all([import('../reader-typography.css').catch(() => {}), import('../pages/Viewer')]).then(([, page]) => page),
  videos: () => import('../pages/Videos'),
  videoViewer: () => Promise.all([import('../reader-typography.css').catch(() => {}), import('../pages/VideoViewer')]).then(([, page]) => page),
  settings: () => import('../pages/Settings'),
  login: () => import('../pages/Login'),
}

export default pages

export function preloadPage(path: string) {
  const load = path === '/library' ? pages.library : path.startsWith('/podcasts/') ? pages.episodes
    : path.startsWith('/viewer/') ? pages.viewer
    : path.startsWith('/videos/') ? pages.videoViewer
    : path === '/podcasts' ? pages.podcasts : path === '/videos' ? pages.videos
    : path === '/settings' ? pages.settings : path === '/login' ? pages.login : pages.dashboard
  void load().catch(() => { /* Navigation retains its normal load/error handling. */ })
}
