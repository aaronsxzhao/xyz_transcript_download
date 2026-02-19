import { useState, useEffect, useRef, useCallback } from 'react'
import { Cpu, MessageSquare, Clock, Loader2, CheckCircle, Trash2, AlertTriangle, Search, Save, Download, X, Activity, Cookie, QrCode, Smartphone } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { fetchSettings, updateSettings, authFetch, importUserSubscriptions, ImportSubscriptionsResult, fetchSysHealth, fetchAllCookies, updateCookie, bilibiliQrGenerate, bilibiliQrPoll } from '../lib/api'

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

// LLM model options — these are LiteLLM model identifiers routed through the proxy
const LLM_MODELS = [
  { value: '', label: 'Server Default' },
  // Vertex AI (direct)
  { value: 'vertex_ai/gemini-3-pro-preview', label: 'Gemini 3 Pro' },
  { value: 'vertex_ai/gemini-3-flash-preview', label: 'Gemini 3 Flash' },
  { value: 'vertex_ai/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'vertex_ai/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
  { value: 'vertex_ai/gemini-2.5-flash-image', label: 'Gemini 2.5 Flash Image' },
  { value: 'vertex_ai/gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
  { value: 'vertex_ai/gemini-2.5-flash-lite-preview-09-2025', label: 'Gemini 2.5 Flash Lite (09-2025)' },
  // Gemini (Firebase)
  { value: 'gemini-2.5-flash-fb', label: 'Gemini 2.5 Flash (Firebase)' },
  { value: 'gemini-2.5-pro-fb', label: 'Gemini 2.5 Pro (Firebase)' },
  // OpenRouter — OpenAI
  { value: 'openrouter/openai/gpt-4o', label: 'GPT-4o (OpenRouter)' },
  { value: 'openrouter/openai/gpt-5-chat', label: 'GPT-5 (OpenRouter)' },
  { value: 'openrouter/openai/gpt-5-mini', label: 'GPT-5 Mini (OpenRouter)' },
  { value: 'openrouter/openai/o3-mini', label: 'o3-mini (OpenRouter)' },
  // OpenRouter — Anthropic
  { value: 'openrouter/anthropic/claude-sonnet-4', label: 'Claude Sonnet 4 (OpenRouter)' },
  { value: 'openrouter/anthropic/claude-sonnet-4.5', label: 'Claude Sonnet 4.5 (OpenRouter)' },
  // OpenRouter — Google
  { value: 'openrouter/google/gemini-2.5-flash', label: 'Gemini 2.5 Flash (OpenRouter)' },
  { value: 'openrouter/google/gemini-2.5-pro', label: 'Gemini 2.5 Pro (OpenRouter)' },
  // OpenRouter — xAI
  { value: 'openrouter/x-ai/grok-3-mini', label: 'Grok 3 Mini (OpenRouter)' },
  { value: 'openrouter/x-ai/grok-4', label: 'Grok 4 (OpenRouter)' },
  { value: 'openrouter/x-ai/grok-4-fast', label: 'Grok 4 Fast (OpenRouter)' },
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
  
  // Import subscriptions state
  const [importUsername, setImportUsername] = useState('')
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportSubscriptionsResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  
  // System health state
  const [sysHealth, setSysHealth] = useState<{
    ffmpeg: { available: boolean; version?: string; error?: string }
    ytdlp: { available: boolean; version?: string; error?: string }
  } | null>(null)
  const [checkingHealth, setCheckingHealth] = useState(false)
  
  // Cookie management state
  const [cookies, setCookies] = useState<{ platform: string; has_cookie: boolean; updated_at: string }[]>([])
  const [cookiePlatform, setCookiePlatform] = useState('bilibili')
  const [cookieData, setCookieData] = useState('')
  const [savingCookie, setSavingCookie] = useState(false)
  
  // BiliBili QR code login state
  const QR_LIFETIME = 120
  const [qrUrl, setQrUrl] = useState('')
  const [qrStatus, setQrStatus] = useState<'idle' | 'loading' | 'waiting' | 'scanned' | 'success' | 'expired' | 'error'>('idle')
  const [qrMessage, setQrMessage] = useState('')
  const [qrCountdown, setQrCountdown] = useState(0)
  const qrPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrAutoRef = useRef(0)
  const qrScannedRef = useRef(false)

  const stopQrPolling = useCallback(() => {
    if (qrPollRef.current) { clearInterval(qrPollRef.current); qrPollRef.current = null }
    if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }
    qrAutoRef.current = 0
    qrScannedRef.current = false
  }, [])

  const startBilibiliQrLogin = useCallback(async () => {
    stopQrPolling()
    setQrStatus('loading')
    setQrMessage('')
    qrScannedRef.current = false
    const autoId = ++qrAutoRef.current

    const generate = async (): Promise<boolean> => {
      if (qrAutoRef.current !== autoId) return false
      try {
        const { qr_url, qrcode_key } = await bilibiliQrGenerate()
        if (qrAutoRef.current !== autoId) return false
        setQrUrl(qr_url)
        setQrStatus('waiting')
        setQrMessage('Open BiliBili app and scan the QR code')
        setQrCountdown(QR_LIFETIME)
        qrScannedRef.current = false

        if (qrTimerRef.current) clearInterval(qrTimerRef.current)
        qrTimerRef.current = setInterval(() => {
          setQrCountdown(prev => {
            if (prev <= 1) return 0
            return prev - 1
          })
        }, 1000)

        if (qrPollRef.current) clearInterval(qrPollRef.current)
        qrPollRef.current = setInterval(async () => {
          if (qrAutoRef.current !== autoId) return
          try {
            const result = await bilibiliQrPoll(qrcode_key)
            if (qrAutoRef.current !== autoId) return
            if (result.status === 'success') {
              setQrStatus('success')
              setQrMessage('Login successful! BiliBili cookies saved.')
              stopQrPolling()
              const data = await fetchAllCookies()
              setCookies(data.cookies)
            } else if (result.status === 'scanned') {
              qrScannedRef.current = true
              setQrStatus('scanned')
              setQrMessage('Scanned! Please confirm on your phone...')
              if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }
              setQrCountdown(0)
            } else if (result.status === 'expired') {
              if (qrScannedRef.current) {
                setQrStatus('error')
                setQrMessage('Confirmation timed out. Please try again.')
                stopQrPolling()
              } else {
                if (qrPollRef.current) clearInterval(qrPollRef.current)
                if (qrTimerRef.current) clearInterval(qrTimerRef.current)
                generate()
              }
            }
          } catch {
            // ignore transient errors, keep polling
          }
        }, 2000)
        return true
      } catch {
        if (qrAutoRef.current === autoId) {
          setQrStatus('error')
          setQrMessage('Failed to generate QR code. Check your network connection.')
        }
        return false
      }
    }

    await generate()
  }, [stopQrPolling])

  useEffect(() => {
    return () => stopQrPolling()
  }, [stopQrPolling])
  
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
  
  async function handleImportSubscriptions() {
    if (!importUsername.trim()) return
    
    setImporting(true)
    setImportError(null)
    setImportResult(null)
    
    try {
      const result = await importUserSubscriptions(importUsername.trim())
      setImportResult(result)
      setImportUsername('')  // Clear input on success
    } catch (err) {
      console.error('Failed to import subscriptions:', err)
      setImportError(err instanceof Error ? err.message : 'Failed to import subscriptions')
    } finally {
      setImporting(false)
    }
  }
  
  function clearImportResults() {
    setImportResult(null)
    setImportError(null)
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
          Transcription (Whisper)
        </h2>
        
        <div className="space-y-4">
          <SettingRow label="Provider" value={settings?.whisper_mode === 'api' ? 'Groq API (cloud)' : 'Local model'} />
          
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
              {LLM_MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
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
      
      {/* Import Subscriptions */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Download className="text-cyan-500" size={20} />
          Import Xiaoyuzhou Subscriptions
        </h2>
        
        <p className="text-sm text-gray-400 mb-4">
          Import all podcasts you subscribe to on Xiaoyuzhou (小宇宙). Enter your username or 
          profile URL below. <span className="text-yellow-400">Your profile must be set to public</span> for 
          this to work. No login tokens are required.
        </p>
        
        <div className="flex gap-3 mb-4">
          <input
            type="text"
            value={importUsername}
            onChange={(e) => setImportUsername(e.target.value)}
            placeholder="Username or profile URL"
            className="flex-1 bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
            onKeyDown={(e) => e.key === 'Enter' && !importing && handleImportSubscriptions()}
          />
          <button
            onClick={handleImportSubscriptions}
            disabled={importing || !importUsername.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {importing ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Download size={16} />
            )}
            Import
          </button>
        </div>
        
        {/* Import Error */}
        {importError && (
          <div className="p-3 rounded-lg mb-4 bg-red-500/10 border border-red-500/30 text-red-300">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle size={16} />
                {importError}
              </div>
              <button onClick={clearImportResults} className="text-red-400 hover:text-red-300">
                <X size={16} />
              </button>
            </div>
          </div>
        )}
        
        {/* Import Results */}
        {importResult && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-300">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <CheckCircle size={16} />
                  Import Complete
                </div>
                <button onClick={clearImportResults} className="text-green-400 hover:text-green-300">
                  <X size={16} />
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                <div>
                  <span className="text-gray-400">Found:</span>{' '}
                  <span className="text-white font-medium">{importResult.total_found}</span>
                </div>
                <div>
                  <span className="text-gray-400">Added:</span>{' '}
                  <span className="text-green-400 font-medium">{importResult.newly_added}</span>
                </div>
                <div>
                  <span className="text-gray-400">Existing:</span>{' '}
                  <span className="text-yellow-400 font-medium">{importResult.already_subscribed}</span>
                </div>
                {importResult.failed > 0 && (
                  <div>
                    <span className="text-gray-400">Failed:</span>{' '}
                    <span className="text-red-400 font-medium">{importResult.failed}</span>
                  </div>
                )}
              </div>
            </div>
            
            {/* List of imported podcasts */}
            {importResult.podcasts.length > 0 && (
              <div className="max-h-48 overflow-y-auto">
                <p className="text-sm text-gray-400 mb-2">Newly imported podcasts:</p>
                <div className="space-y-1">
                  {importResult.podcasts.map((name, idx) => (
                    <div key={idx} className="text-sm text-white py-1 px-2 bg-dark-hover rounded">
                      {name}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        
        <p className="text-xs text-gray-500 mt-4">
          Tip: Find your username in your Xiaoyuzhou profile URL 
          (e.g., xiaoyuzhoufm.com/user/<span className="text-cyan-400">your_username</span>)
        </p>
      </div>
      
      {/* System Health (for Video Notes) */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Activity className="text-emerald-500" size={20} />
          Video Tools Health
        </h2>
        
        <p className="text-sm text-gray-400 mb-4">
          Check system dependencies required for video note generation.
        </p>
        
        <button
          onClick={async () => {
            setCheckingHealth(true)
            try {
              const data = await fetchSysHealth()
              setSysHealth(data)
            } catch (e) {
              console.error('Health check failed:', e)
            } finally {
              setCheckingHealth(false)
            }
          }}
          disabled={checkingHealth}
          className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50 mb-4"
        >
          {checkingHealth ? <Loader2 size={16} className="animate-spin" /> : <Activity size={16} />}
          Check Health
        </button>
        
        {sysHealth && (
          <div className="space-y-3">
            <div className={`p-3 rounded-lg flex items-center gap-3 ${
              sysHealth.ffmpeg.available ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
            }`}>
              <span className={sysHealth.ffmpeg.available ? 'text-green-400' : 'text-red-400'}>
                {sysHealth.ffmpeg.available ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
              </span>
              <div>
                <p className={`text-sm font-medium ${sysHealth.ffmpeg.available ? 'text-green-300' : 'text-red-300'}`}>
                  FFmpeg
                </p>
                <p className="text-xs text-gray-400">
                  {sysHealth.ffmpeg.available ? sysHealth.ffmpeg.version : sysHealth.ffmpeg.error}
                </p>
              </div>
            </div>
            <div className={`p-3 rounded-lg flex items-center gap-3 ${
              sysHealth.ytdlp.available ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
            }`}>
              <span className={sysHealth.ytdlp.available ? 'text-green-400' : 'text-red-400'}>
                {sysHealth.ytdlp.available ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
              </span>
              <div>
                <p className={`text-sm font-medium ${sysHealth.ytdlp.available ? 'text-green-300' : 'text-red-300'}`}>
                  yt-dlp
                </p>
                <p className="text-xs text-gray-400">
                  {sysHealth.ytdlp.available ? `v${sysHealth.ytdlp.version}` : sysHealth.ytdlp.error}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
      
      {/* BiliBili QR Code Login */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <QrCode className="text-pink-500" size={20} />
          BiliBili Login
        </h2>
        
        <p className="text-sm text-gray-400 mb-4">
          Scan the QR code with the BiliBili mobile app to authenticate.
          This is required for downloading BiliBili video content.
        </p>

        <div className="space-y-4">
          {qrStatus === 'idle' || qrStatus === 'error' ? (
            <div>
              <button
                onClick={startBilibiliQrLogin}
                className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors"
              >
                <Smartphone size={16} />
                Generate QR Code
              </button>
              {qrStatus === 'error' && qrMessage && (
                <p className="text-sm text-amber-400 mt-2">{qrMessage}</p>
              )}
            </div>
          ) : qrStatus === 'loading' ? (
            <div className="flex items-center gap-2 text-gray-400">
              <Loader2 size={16} className="animate-spin" />
              Generating QR code...
            </div>
          ) : qrStatus === 'success' ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-green-400">
                <CheckCircle size={16} />
                {qrMessage}
              </div>
              <button
                onClick={startBilibiliQrLogin}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Re-login
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-col items-center gap-3 p-4 bg-white rounded-xl w-fit mx-auto relative">
                <QRCodeSVG value={qrUrl} size={200} level="M" />
              </div>
              <div className="text-center space-y-1">
                <p className={`text-sm ${qrStatus === 'scanned' ? 'text-cyan-400' : 'text-gray-400'}`}>
                  {qrStatus === 'scanned' ? (
                    <span className="flex items-center justify-center gap-2">
                      <Smartphone size={14} />
                      Scanned! Confirm on your phone...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-2">
                      <Loader2 size={14} className="animate-spin" />
                      Waiting for scan...
                    </span>
                  )}
                </p>
                {qrStatus === 'waiting' && qrCountdown > 0 && (
                  <p className="text-xs text-gray-500">
                    {qrCountdown > 10
                      ? `Auto-refreshes in ${qrCountdown}s`
                      : <span className="text-amber-400">Refreshing in {qrCountdown}s...</span>
                    }
                  </p>
                )}
              </div>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={startBilibiliQrLogin}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  Refresh now
                </button>
                <button
                  onClick={() => { stopQrPolling(); setQrStatus('idle'); setQrUrl('') }}
                  className="text-xs text-gray-500 hover:text-red-400 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Cookie Management */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Cookie className="text-amber-500" size={20} />
          Platform Cookies (Manual)
        </h2>
        
        <p className="text-sm text-gray-400 mb-4">
          For other platforms or manual cookie setup. Paste Netscape-format cookies here.
        </p>
        
        <div className="space-y-3">
          <div className="flex gap-2">
            <select
              value={cookiePlatform}
              onChange={e => setCookiePlatform(e.target.value)}
              className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2"
            >
              <option value="bilibili">Bilibili</option>
              <option value="youtube">YouTube</option>
              <option value="douyin">Douyin</option>
              <option value="kuaishou">Kuaishou</option>
            </select>
            <button
              onClick={async () => {
                try {
                  const data = await fetchAllCookies()
                  setCookies(data.cookies)
                } catch (e) {
                  console.error('Failed to fetch cookies:', e)
                }
              }}
              className="px-3 py-2 bg-dark-hover hover:bg-dark-border text-sm text-gray-300 rounded-lg transition-colors"
            >
              Refresh
            </button>
          </div>
          
          <textarea
            value={cookieData}
            onChange={e => setCookieData(e.target.value)}
            placeholder="Paste cookie string here..."
            rows={3}
            className="w-full px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-amber-500 resize-none font-mono"
          />
          
          <button
            onClick={async () => {
              setSavingCookie(true)
              try {
                await updateCookie(cookiePlatform, cookieData)
                setCookieData('')
                const data = await fetchAllCookies()
                setCookies(data.cookies)
              } catch (e) {
                console.error('Failed to save cookie:', e)
              } finally {
                setSavingCookie(false)
              }
            }}
            disabled={savingCookie || !cookieData.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {savingCookie ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Cookie
          </button>
          
          {cookies.length > 0 && (
            <div className="space-y-1 mt-2">
              <p className="text-xs text-gray-500">Stored cookies:</p>
              {cookies.map(c => (
                <div key={c.platform} className="flex items-center justify-between p-2 bg-dark-hover rounded text-sm">
                  <span className="text-white capitalize">{c.platform}</span>
                  <span className={`text-xs ${c.has_cookie ? 'text-green-400' : 'text-gray-500'}`}>
                    {c.has_cookie ? 'Configured' : 'Not set'}
                  </span>
                </div>
              ))}
            </div>
          )}
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
