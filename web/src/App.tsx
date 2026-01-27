import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Podcasts from './pages/Podcasts'
import Episodes from './pages/Episodes'
import Viewer from './pages/Viewer'
import Settings from './pages/Settings'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/podcasts" element={<Podcasts />} />
        <Route path="/podcasts/:pid/episodes" element={<Episodes />} />
        <Route path="/viewer/:eid" element={<Viewer />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  )
}

export default App
