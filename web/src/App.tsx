import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, authEnabled } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  // If auth is not enabled (local mode), allow access
  if (!authEnabled) {
    return <>{children}</>
  }

  // If auth is enabled but user is not logged in, redirect to login
  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
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
        <Route path="/" element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>} />
        <Route path="/podcasts" element={<ProtectedRoute><Layout><Podcasts /></Layout></ProtectedRoute>} />
        <Route path="/podcasts/:pid/episodes" element={<ProtectedRoute><Layout><Episodes /></Layout></ProtectedRoute>} />
        <Route path="/viewer/:eid" element={<ProtectedRoute><Layout><Viewer /></Layout></ProtectedRoute>} />
        <Route path="/videos" element={<ProtectedRoute><Layout><Videos /></Layout></ProtectedRoute>} />
        <Route path="/videos/:taskId" element={<ProtectedRoute><Layout><VideoViewer /></Layout></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Layout><Settings /></Layout></ProtectedRoute>} />
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
