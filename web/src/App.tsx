import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, Outlet, Link, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import TopNav from './components/TopNav'
import { Loader2 } from 'lucide-react'
import pages, { preloadPage } from './lib/pages'
import { getAuthConfig } from './lib/auth'
import { markPageNavigation } from './lib/pageTiming'

// Start these independent requests together instead of fetching the route only
// after config/session verification has finished.
preloadPage(window.location.pathname)
void getAuthConfig().catch(() => {})
const ResetPassword = lazy(pages.resetPassword)
const Library = lazy(pages.library)
const Dashboard = lazy(pages.dashboard)
const Podcasts = lazy(pages.podcasts)
const Episodes = lazy(pages.episodes)
const Viewer = lazy(pages.viewer)
const Videos = lazy(pages.videos)
const VideoViewer = lazy(pages.videoViewer)
const Settings = lazy(pages.settings)
const Login = lazy(pages.login)

function LoadingFrame() {
  return <div className="min-h-screen bg-dark-bg text-gray-100"><TopNav /><main className="p-4 md:p-6"><div role="status" className="flex items-center gap-3 py-8"><Loader2 className="animate-spin text-indigo-400" size={22} />Connecting to your workspace…</div></main></div>
}

function ProtectedRoute() {
  const { user, loading, authEnabled } = useAuth()

  if (loading) {
    return <LoadingFrame />
  }

  if (!authEnabled) {
    return <Outlet />
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}

const PageSpinner = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
  </div>
)

function AppRoutes() {
  const { authEnabled, user, loading } = useAuth()
  const location = useLocation()
  markPageNavigation(location.pathname + location.search)

  if (loading) {
    return <LoadingFrame />
  }

  return (
    <Suspense fallback={<PageSpinner />}>
      <Routes key={user?.id || 'signed-out'}>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route
          path="/login"
          element={
            authEnabled && !user ? (
              <Login />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/library" element={<Library />} />
            <Route path="/podcasts" element={<Podcasts />} />
            <Route path="/podcasts/:pid/episodes" element={<Episodes />} />
            <Route path="/viewer/:eid" element={<Viewer />} />
            <Route path="/videos" element={<Videos />} />
            <Route path="/videos/:taskId" element={<VideoViewer />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<div className="space-y-3"><h1 className="text-xl font-semibold">Page not found</h1><Link to="/" className="text-indigo-300 underline">Return to dashboard</Link></div>} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}

export default App
