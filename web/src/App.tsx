import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Podcasts from './pages/Podcasts'
import Episodes from './pages/Episodes'
import Viewer from './pages/Viewer'
import Videos from './pages/Videos'
import VideoViewer from './pages/VideoViewer'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { Loader2 } from 'lucide-react'

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
    <Routes>
      {/* Login route - only show if auth is enabled */}
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
      
      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout>
              <Dashboard />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/podcasts"
        element={
          <ProtectedRoute>
            <Layout>
              <Podcasts />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/podcasts/:pid/episodes"
        element={
          <ProtectedRoute>
            <Layout>
              <Episodes />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/viewer/:eid"
        element={
          <ProtectedRoute>
            <Layout>
              <Viewer />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/videos"
        element={
          <ProtectedRoute>
            <Layout>
              <Videos />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/videos/:taskId"
        element={
          <ProtectedRoute>
            <Layout>
              <VideoViewer />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Layout>
              <Settings />
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
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
