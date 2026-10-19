const pages = {
  dashboard: () => import('../pages/Dashboard'),
  podcasts: () => import('../pages/Podcasts'),
  episodes: () => import('../pages/Episodes'),
  viewer: () => import('../pages/Viewer'),
  videos: () => import('../pages/Videos'),
  videoViewer: () => import('../pages/VideoViewer'),
  settings: () => import('../pages/Settings'),
  login: () => import('../pages/Login'),
}

export default pages

export function preloadPage(path: string) {
  const load = path.startsWith('/podcasts/') ? pages.episodes
    : path.startsWith('/viewer/') ? pages.viewer
    : path.startsWith('/videos/') ? pages.videoViewer
    : path === '/podcasts' ? pages.podcasts : path === '/videos' ? pages.videos
    : path === '/settings' ? pages.settings : path === '/login' ? pages.login : pages.dashboard
  void load().catch(() => { /* Navigation retains its normal load/error handling. */ })
}
