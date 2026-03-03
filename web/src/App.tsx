import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import { Loader2 } from 'lucide-react'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Podcasts = lazy(() => import('./pages/Podcasts'))
const Episodes = lazy(() => import('./pages/Episodes'))
const Viewer = lazy(() => import('./pages/Viewer'))
const Videos = lazy(() => import('./pages/Videos'))
const VideoViewer = lazy(() => import('./pages/VideoViewer'))
const Settings = lazy(() => import('./pages/Settings'))
const Login = lazy(() => import('./pages/Login'))

function ProtectedRoute() {
  const { user, loading, authEnabled } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
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

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  return (
    <Suspense fallback={<PageSpinner />}>
      <Routes>
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
            <Route path="/podcasts" element={<Podcasts />} />
            <Route path="/podcasts/:pid/episodes" element={<Episodes />} />
            <Route path="/viewer/:eid" element={<Viewer />} />
            <Route path="/videos" element={<Videos />} />
            <Route path="/videos/:taskId" element={<VideoViewer />} />
            <Route path="/settings" element={<Settings />} />
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
