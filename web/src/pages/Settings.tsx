import { useState, useEffect } from 'react'
import { Cpu, MessageSquare, Clock, Loader2, CheckCircle, Trash2, AlertTriangle, Search, Save } from 'lucide-react'
import { fetchSettings, updateSettings, authFetch } from '../lib/api'

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

// Whisper model options
const WHISPER_MODELS = [
  { value: 'whisper-large-v3', label: 'whisper-large-v3', description: 'More accurate, slower' },
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo', description: 'Faster, slightly less accurate' },
]

// LLM model options
const LLM_MODELS = [
  'openrouter/openai/gpt-4o',
  'openrouter/openai/gpt-5-chat',
  'openrouter/openai/gpt-5-mini',
  'openrouter/openai/o3-mini',
  'openrouter/anthropic/claude-sonnet-4',
  'openrouter/anthropic/claude-sonnet-4.5',
  'openrouter/google/gemini-2.5-flash',
  'openrouter/google/gemini-2.5-pro',
  'openrouter/x-ai/grok-3-mini',
  'openrouter/x-ai/grok-4',
  'openrouter/x-ai/grok-4-fast',
  'vertex_ai/gemini-2.5-flash',
  'vertex_ai/gemini-2.5-flash-image',
  'vertex_ai/gemini-2.5-flash-lite',
  'vertex_ai/gemini-2.5-flash-lite-preview-09-2025',
  'vertex_ai/gemini-2.5-pro',
  'vertex_ai/gemini-3-pro-preview',
  'vertex_ai/gemini-3-flash-preview',
  'gemini-2.5-flash-fb',
  'gemini-2.5-pro-fb',
]

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Editable settings state
  const [whisperModel, setWhisperModel] = useState<string>('')
  const [llmModel, setLlmModel] = useState<string>('')
  const [maxOutputTokens, setMaxOutputTokens] = useState<string>('16000')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  
  // Data maintenance state
  const [truncatedItems, setTruncatedItems] = useState<TruncatedItem[]>([])
  const [checking, setChecking] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)
  
  useEffect(() => {
    loadSettings()
  }, [])
  
  // Initialize editable settings when settings are loaded
  useEffect(() => {
    if (settings) {
      // Load from localStorage first, then fall back to server settings
      const savedWhisperModel = localStorage.getItem('whisper_model') || settings.whisper_model
      const savedLlmModel = localStorage.getItem('llm_model') || settings.llm_model
      const savedMaxTokens = localStorage.getItem('max_output_tokens')
      setWhisperModel(savedWhisperModel)
      setLlmModel(savedLlmModel)
      setMaxOutputTokens(savedMaxTokens || '16000')
    }
  }, [settings])
  
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
  
  async function saveSettings() {
    setSaving(true)
    setSaveResult(null)
    try {
      // Validate max tokens
      const parsedTokens = parseInt(maxOutputTokens, 10) || 16000
      const validTokens = Math.max(4000, Math.min(32000, parsedTokens))
      
      // Save to localStorage for persistence
      localStorage.setItem('whisper_model', whisperModel)
      localStorage.setItem('llm_model', llmModel)
      localStorage.setItem('max_output_tokens', validTokens.toString())
      
      // Also update server settings
      await updateSettings({ 
        whisper_model: whisperModel, 
        llm_model: llmModel,
        max_output_tokens: validTokens,
      })
      
      setSaveResult('Settings saved successfully!')
      setTimeout(() => setSaveResult(null), 3000)
    } catch (err) {
      console.error('Failed to save settings:', err)
      setSaveResult('Failed to save settings')
    } finally {
      setSaving(false)
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
          
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
            <span className="text-gray-400">Model</span>
            <select
              value={whisperModel}
              onChange={(e) => setWhisperModel(e.target.value)}
              className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent w-full sm:w-auto"
            >
              {WHISPER_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label}
                </option>
              ))}
            </select>
          </div>
          
          <p className="text-xs text-gray-500">
            {WHISPER_MODELS.find(m => m.value === whisperModel)?.description || 'Select a model'}
          </p>
        </div>
        
      </div>
      
      {/* LLM Settings */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <MessageSquare className="text-purple-500" size={20} />
          LLM Configuration
        </h2>
        
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
            <span className="text-gray-400">Model</span>
            <select
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 focus:border-transparent w-full sm:w-auto sm:max-w-[220px] truncate"
            >
              {LLM_MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
          
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
            <div className="flex flex-col">
              <span className="text-gray-400">Max Output Tokens</span>
              <span className="text-xs text-gray-500">Higher = more detailed summaries</span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={maxOutputTokens}
                onChange={(e) => setMaxOutputTokens(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="16000"
                className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 focus:border-transparent w-28 text-right"
              />
              <span className="text-xs text-gray-500 hidden sm:inline">tokens</span>
            </div>
          </div>
          
          <p className="text-xs text-gray-500">
            Recommended: 16,000 for 1-2hr podcasts, 24,000+ for longer episodes
          </p>
        </div>
      </div>
      
      {/* Save Button */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={saveSettings}
          disabled={saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
        >
          {saving ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Save size={16} />
          )}
          Save Settings
        </button>
        
        {saveResult && (
          <span className={`text-sm ${saveResult.includes('Failed') ? 'text-red-400' : 'text-green-400'}`}>
            {saveResult}
          </span>
        )}
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
