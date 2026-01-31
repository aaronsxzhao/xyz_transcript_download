import { useState, useEffect } from 'react'
import { Cpu, MessageSquare, Clock, Loader2, CheckCircle, Trash2, AlertTriangle, Search } from 'lucide-react'
import { fetchSettings, authFetch } from '../lib/api'

interface SettingsData {
  whisper_mode: string
  whisper_model: string
  whisper_backend: string
  whisper_device: string
  llm_model: string
  check_interval: number
}

interface TruncatedItem {
  episode_id: string
  pid: string
  episode_title: string
  episode_duration: number
  transcript_duration: number
  percentage: number
}

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Data maintenance state
  const [truncatedItems, setTruncatedItems] = useState<TruncatedItem[]>([])
  const [checking, setChecking] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)
  
  useEffect(() => {
    loadSettings()
  }, [])
  
  async function loadSettings() {
    try {
      const data = await fetchSettings()
      setSettings(data)
    } catch (err) {
      console.error('Failed to load settings:', err)
    } finally {
      setLoading(false)
    }
  }
  
  async function checkTruncated() {
    setChecking(true)
    setCleanupResult(null)
    try {
      const response = await authFetch('/api/truncated')
      if (response.ok) {
        const data = await response.json()
        setTruncatedItems(data.truncated || [])
        if (data.truncated.length === 0) {
          setCleanupResult('No truncated transcripts found. All data looks good!')
        }
      }
    } catch (err) {
      console.error('Failed to check truncated:', err)
      setCleanupResult('Failed to check for truncated data')
    } finally {
      setChecking(false)
    }
  }
  
  async function cleanupTruncated() {
    if (!confirm(`This will delete ${truncatedItems.length} truncated transcripts and their summaries. Continue?`)) {
      return
    }
    
    setCleaning(true)
    try {
      const response = await authFetch('/api/truncated/cleanup', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        setCleanupResult(`Cleaned up ${data.deleted.length} truncated transcripts. You can now reprocess these episodes.`)
        setTruncatedItems([])
      }
    } catch (err) {
      console.error('Failed to cleanup:', err)
      setCleanupResult('Failed to clean up truncated data')
    } finally {
      setCleaning(false)
    }
  }
  
  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    return `${mins} min`
  }
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }
  
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Settings</h1>
        <p className="text-gray-400">View current configuration</p>
      </div>
      
      {/* Whisper Settings */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Cpu className="text-blue-500" size={20} />
          Whisper Configuration
        </h2>
        
        <div className="space-y-4">
          <SettingRow label="Mode" value={settings?.whisper_mode || '-'} />
          <SettingRow label="Backend" value={settings?.whisper_backend || '-'} />
          <SettingRow label="Model" value={settings?.whisper_model || '-'} />
          <SettingRow label="Device" value={settings?.whisper_device || '-'} />
        </div>
        
        <p className="mt-4 text-sm text-gray-500">
          To change these settings, edit the <code className="text-indigo-400">.env</code> file and restart the server.
        </p>
      </div>
      
      {/* LLM Settings */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <MessageSquare className="text-purple-500" size={20} />
          LLM Configuration
        </h2>
        
        <div className="space-y-4">
          <SettingRow label="Model" value={settings?.llm_model || '-'} />
        </div>
        
        <p className="mt-4 text-sm text-gray-500">
          Configure LLM API in <code className="text-indigo-400">.env</code> with LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL.
        </p>
      </div>
      
      {/* Daemon Settings */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Clock className="text-green-500" size={20} />
          Daemon Configuration
        </h2>
        
        <div className="space-y-4">
          <SettingRow 
            label="Check Interval" 
            value={settings ? `${Math.floor(settings.check_interval / 60)} minutes` : '-'} 
          />
        </div>
      </div>
      
      {/* Data Maintenance */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Trash2 className="text-red-500" size={20} />
          Data Maintenance
        </h2>
        
        <p className="text-sm text-gray-400 mb-4">
          Check for and clean up truncated transcripts. A transcript is considered truncated 
          if its duration is less than 85% of the episode's expected duration.
        </p>
        
        <div className="flex gap-3 mb-4">
          <button
            onClick={checkTruncated}
            disabled={checking}
            className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {checking ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Search size={16} />
            )}
            Check for Truncated
          </button>
          
          {truncatedItems.length > 0 && (
            <button
              onClick={cleanupTruncated}
              disabled={cleaning}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {cleaning ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Trash2 size={16} />
              )}
              Delete {truncatedItems.length} Truncated
            </button>
          )}
        </div>
        
        {cleanupResult && (
          <div className={`p-3 rounded-lg mb-4 ${
            cleanupResult.includes('Failed') 
              ? 'bg-red-500/10 border border-red-500/30 text-red-300' 
              : 'bg-green-500/10 border border-green-500/30 text-green-300'
          }`}>
            <div className="flex items-center gap-2">
              <CheckCircle size={16} />
              {cleanupResult}
            </div>
          </div>
        )}
        
        {truncatedItems.length > 0 && (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            <p className="text-sm text-yellow-400 flex items-center gap-2 mb-2">
              <AlertTriangle size={16} />
              Found {truncatedItems.length} truncated transcripts:
            </p>
            {truncatedItems.map((item) => (
              <div 
                key={item.episode_id}
                className="p-3 bg-dark-hover rounded-lg text-sm"
              >
                <p className="text-white font-medium truncate">{item.episode_title}</p>
                <p className="text-gray-400 mt-1">
                  Transcript: {formatDuration(item.transcript_duration)} / Expected: {formatDuration(item.episode_duration)} 
                  <span className="text-red-400 ml-2">({item.percentage}%)</span>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Info */}
      <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-xl">
        <div className="flex items-start gap-3">
          <CheckCircle className="text-indigo-500 flex-shrink-0 mt-0.5" size={20} />
          <div>
            <p className="text-indigo-200 font-medium">Configuration via .env file</p>
            <p className="text-sm text-indigo-300/70 mt-1">
              All settings are configured through the <code>.env</code> file in the project root. 
              Changes require a server restart to take effect.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-dark-border last:border-0">
      <span className="text-gray-400">{label}</span>
      <span className="text-white font-mono text-sm">{value}</span>
    </div>
  )
}
