import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Cpu, MessageSquare, Clock, Loader2, CheckCircle, Trash2, AlertTriangle,
  Search, Save, Download, X, Activity, Smartphone, Chrome,
  ExternalLink, Settings2, UserCircle, Wrench, Upload, FileText,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import {
  fetchSettings, updateSettings, authFetch, importUserSubscriptions,
  ImportSubscriptionsResult, fetchSysHealth, fetchAllCookies,
  bilibiliQrGenerate, bilibiliQrPoll, douyinQrGenerate, douyinQrPoll,
  uploadCookieFile, importBrowserCookies, saveSimpleCookie,
} from '../lib/api'

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

const WHISPER_MODELS = [
  { value: 'whisper-large-v3', label: 'whisper-large-v3', description: 'More accurate, slower' },
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo', description: 'Faster, slightly less accurate' },
]

const LLM_MODELS = [
  { value: '', label: 'Server Default' },
  { value: 'vertex_ai/gemini-3-pro-preview', label: 'Gemini 3 Pro' },
  { value: 'vertex_ai/gemini-3-flash-preview', label: 'Gemini 3 Flash' },
  { value: 'vertex_ai/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'vertex_ai/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
  { value: 'vertex_ai/gemini-2.5-flash-image', label: 'Gemini 2.5 Flash Image' },
  { value: 'vertex_ai/gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
  { value: 'vertex_ai/gemini-2.5-flash-lite-preview-09-2025', label: 'Gemini 2.5 Flash Lite (09-2025)' },
  { value: 'gemini-2.5-flash-fb', label: 'Gemini 2.5 Flash (Firebase)' },
  { value: 'gemini-2.5-pro-fb', label: 'Gemini 2.5 Pro (Firebase)' },
  { value: 'openrouter/openai/gpt-4o', label: 'GPT-4o (OpenRouter)' },
  { value: 'openrouter/openai/gpt-5-chat', label: 'GPT-5 (OpenRouter)' },
  { value: 'openrouter/openai/gpt-5-mini', label: 'GPT-5 Mini (OpenRouter)' },
  { value: 'openrouter/openai/o3-mini', label: 'o3-mini (OpenRouter)' },
  { value: 'openrouter/anthropic/claude-sonnet-4', label: 'Claude Sonnet 4 (OpenRouter)' },
  { value: 'openrouter/anthropic/claude-sonnet-4.5', label: 'Claude Sonnet 4.5 (OpenRouter)' },
  { value: 'openrouter/google/gemini-2.5-flash', label: 'Gemini 2.5 Flash (OpenRouter)' },
  { value: 'openrouter/google/gemini-2.5-pro', label: 'Gemini 2.5 Pro (OpenRouter)' },
  { value: 'openrouter/x-ai/grok-3-mini', label: 'Grok 3 Mini (OpenRouter)' },
  { value: 'openrouter/x-ai/grok-4', label: 'Grok 4 (OpenRouter)' },
  { value: 'openrouter/x-ai/grok-4-fast', label: 'Grok 4 Fast (OpenRouter)' },
]

type TopTab = 'general' | 'accounts' | 'tools'

const TOP_TABS: { id: TopTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: 'General', icon: <Settings2 size={16} /> },
  { id: 'accounts', label: 'Platform Accounts', icon: <UserCircle size={16} /> },
  { id: 'tools', label: 'Tools & Data', icon: <Wrench size={16} /> },
]

export default function Settings() {
  const [activeTab, setActiveTab] = useState<TopTab>('general')
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)

  const [whisperModel, setWhisperModel] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const [truncatedItems, setTruncatedItems] = useState<TruncatedItem[]>([])
  const [checking, setChecking] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)

  const [importUsername, setImportUsername] = useState('')
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportSubscriptionsResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const [sysHealth, setSysHealth] = useState<{
    ffmpeg: { available: boolean; version?: string; error?: string }
    ytdlp: { available: boolean; version?: string; error?: string }
  } | null>(null)
  const [checkingHealth, setCheckingHealth] = useState(false)

  const PLATFORMS = ['bilibili', 'youtube', 'douyin', 'kuaishou'] as const
  type Platform = typeof PLATFORMS[number]
  const [activePlatform, setActivePlatform] = useState<Platform>('bilibili')
  const [cookies, setCookies] = useState<{ platform: string; has_cookie: boolean; updated_at: string }[]>([])

  const QR_LIFETIME = 120
  const QR_MAX_AUTO_RETRIES = 3
  const QR_RETRY_DELAY_MS = 2000
  const [qrUrl, setQrUrl] = useState('')
  const [qrStatus, setQrStatus] = useState<'idle' | 'loading' | 'waiting' | 'scanned' | 'success' | 'expired' | 'error'>('idle')
  const [qrMessage, setQrMessage] = useState('')
  const [qrCountdown, setQrCountdown] = useState(0)
  const qrPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrAutoRef = useRef(0)
  const qrScannedRef = useRef(false)
  const qrRetryCountRef = useRef(0)
  const qrPlatformRef = useRef<Platform>('bilibili')

  const [cookieMessage, setCookieMessage] = useState('')
  const [cookieLoading, setCookieLoading] = useState(false)
  const [showFileUpload, setShowFileUpload] = useState(false)
  const [selectedBrowser, setSelectedBrowser] = useState('chrome')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const BROWSERS = [
    { value: 'chrome', label: 'Chrome' },
    { value: 'firefox', label: 'Firefox' },
    { value: 'edge', label: 'Edge' },
    { value: 'safari', label: 'Safari' },
    { value: 'brave', label: 'Brave' },
  ]

  const handleAutoImport = useCallback(async (platform: Platform) => {
    setCookieLoading(true)
    setCookieMessage('')
    try {
      const result = await importBrowserCookies(platform, selectedBrowser)
      if (result.success) {
        setCookieMessage(`✅ ${result.message}`)
        const data = await fetchAllCookies()
        setCookies(data.cookies)
      } else {
        setCookieMessage(`⚠️ ${result.message}`)
        setShowFileUpload(true)
      }
    } catch (err) {
      setCookieMessage(`❌ ${err instanceof Error ? err.message : 'Import failed'}`)
      setShowFileUpload(true)
    } finally {
      setCookieLoading(false)
    }
  }, [selectedBrowser])

  const handleCookieFileUpload = useCallback(async (platform: Platform, file: File) => {
    setCookieLoading(true)
    setCookieMessage('')
    try {
      const result = await uploadCookieFile(platform, file)
      setCookieMessage(`✅ ${result.message}`)
      const data = await fetchAllCookies()
      setCookies(data.cookies)
    } catch (err) {
      setCookieMessage(`❌ ${err instanceof Error ? err.message : 'Upload failed'}`)
    } finally {
      setCookieLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [])

  const stopQrPolling = useCallback(() => {
    if (qrPollRef.current) { clearInterval(qrPollRef.current); qrPollRef.current = null }
    if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }
    qrAutoRef.current = 0
    qrScannedRef.current = false
    qrRetryCountRef.current = 0
  }, [])

  const startQrLogin = useCallback(async (platform: 'bilibili' | 'douyin', isManual = true) => {
    if (isManual) {
      stopQrPolling()
      qrRetryCountRef.current = 0
    } else {
      if (qrPollRef.current) { clearInterval(qrPollRef.current); qrPollRef.current = null }
      if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }
    }

    setQrStatus('loading')
    if (isManual) setQrMessage('')
    qrScannedRef.current = false
    qrPlatformRef.current = platform
    const autoId = isManual ? ++qrAutoRef.current : qrAutoRef.current

    const generateFn = platform === 'bilibili' ? bilibiliQrGenerate : douyinQrGenerate
    const pollFn = platform === 'bilibili'
      ? (key: string) => bilibiliQrPoll(key)
      : (key: string) => douyinQrPoll(key)
    const appName = platform === 'bilibili' ? 'BiliBili' : 'Douyin'

    try {
      const result = await generateFn()
      if (qrAutoRef.current !== autoId) return
      const url = 'qr_url' in result ? result.qr_url : ''
      const key = platform === 'bilibili'
        ? (result as { qrcode_key: string }).qrcode_key
        : (result as { token: string }).token
      setQrUrl(url)
      setQrStatus('waiting')
      setQrMessage(
        qrRetryCountRef.current > 0
          ? `New QR code ready (attempt ${qrRetryCountRef.current + 1}) — scan and confirm quickly`
          : `Open ${appName} app and scan the QR code`
      )
      setQrCountdown(QR_LIFETIME)
      qrScannedRef.current = false

      qrTimerRef.current = setInterval(() => {
        setQrCountdown(prev => prev <= 1 ? 0 : prev - 1)
      }, 1000)

      qrPollRef.current = setInterval(async () => {
        if (qrAutoRef.current !== autoId) return
        try {
          const poll = await pollFn(key)
          if (qrAutoRef.current !== autoId) return
          if (poll.status === 'success') {
            setQrStatus('success')
            setQrMessage(`Login successful! ${appName} cookies saved.`)
            stopQrPolling()
            const data = await fetchAllCookies()
            setCookies(data.cookies)
          } else if (poll.status === 'scanned') {
            qrScannedRef.current = true
            setQrStatus('scanned')
            setQrMessage(`Scanned! Please confirm on your phone quickly (${appName} QR codes expire fast)...`)
            if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }
            setQrCountdown(0)
          } else if (poll.status === 'expired') {
            if (qrPollRef.current) { clearInterval(qrPollRef.current); qrPollRef.current = null }
            if (qrTimerRef.current) { clearInterval(qrTimerRef.current); qrTimerRef.current = null }

            qrRetryCountRef.current++
            if (qrRetryCountRef.current >= QR_MAX_AUTO_RETRIES) {
              setQrStatus('expired')
              setQrMessage(
                qrScannedRef.current
                  ? `QR expired ${QR_MAX_AUTO_RETRIES} times — you scanned but didn't confirm fast enough. Click "Generate QR Code" to try again.`
                  : `QR expired ${QR_MAX_AUTO_RETRIES} times. Click "Generate QR Code" to try again.`
              )
              qrRetryCountRef.current = 0
              return
            }

            if (qrScannedRef.current) {
              setQrMessage('QR expired before confirmation — generating a new one, please confirm faster...')
            } else {
              setQrMessage('QR expired, generating a new one...')
            }
            setQrStatus('loading')

            await new Promise(r => setTimeout(r, QR_RETRY_DELAY_MS))
            if (qrAutoRef.current !== autoId) return
            startQrLogin(platform, false)
          } else if (poll.status === 'waiting') {
            if (poll.message && poll.message !== 'Waiting for scan') {
              setQrMessage(poll.message)
            }
          }
        } catch (err) {
          console.warn('QR poll error:', err)
        }
      }, 2000)
    } catch {
      if (qrAutoRef.current === autoId) {
        setQrStatus('error')
        setQrMessage(
          qrRetryCountRef.current > 0
            ? `Failed to generate QR code after ${qrRetryCountRef.current + 1} attempts. ${appName} may be rate-limiting. Wait a moment and try again.`
            : 'Failed to generate QR code. Check your network connection.'
        )
        qrRetryCountRef.current = 0
      }
    }
  }, [stopQrPolling])

  const handleSwitchPlatform = useCallback((p: Platform) => {
    stopQrPolling()
    setQrStatus('idle')
    setQrUrl('')
    setQrMessage('')
    setCookieMessage('')
    setShowFileUpload(false)
    setActivePlatform(p)
  }, [stopQrPolling])

  useEffect(() => {
    return () => { stopQrPolling() }
  }, [stopQrPolling])

  useEffect(() => { loadSettings() }, [])

  useEffect(() => {
    fetchAllCookies()
      .then(data => setCookies(data.cookies))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (settings) {
      const savedWhisperModel = localStorage.getItem('whisper_model') || settings.whisper_model
      const savedLlmModel = localStorage.getItem('llm_model') || settings.llm_model
      setWhisperModel(savedWhisperModel)
      setLlmModel(savedLlmModel)
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
      localStorage.setItem('whisper_model', whisperModel)
      localStorage.setItem('llm_model', llmModel)
      await updateSettings({
        whisper_model: whisperModel,
        llm_model: llmModel,
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
    if (!confirm(`This will delete ${truncatedItems.length} truncated transcripts and their summaries. Continue?`)) return
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
    return `${Math.floor(seconds / 60)} min`
  }

  async function handleImportSubscriptions() {
    if (!importUsername.trim()) return
    setImporting(true)
    setImportError(null)
    setImportResult(null)
    try {
      const result = await importUserSubscriptions(importUsername.trim())
      setImportResult(result)
      setImportUsername('')
    } catch (err) {
      console.error('Failed to import subscriptions:', err)
      setImportError(err instanceof Error ? err.message : 'Failed to import subscriptions')
    } finally {
      setImporting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  const platformLabel = (p: string) =>
    p === 'bilibili' ? 'BiliBili' : p === 'youtube' ? 'YouTube' : p.charAt(0).toUpperCase() + p.slice(1)

  return (
    <div className="max-w-2xl">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white mb-1">Settings</h1>
        <p className="text-sm text-gray-500">Configure AI models, platform logins, and system tools</p>
      </div>

      {/* Top-level tab bar */}
      <div className="flex gap-1 p-1 bg-dark-surface border border-dark-border rounded-xl mb-5">
        {TOP_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-dark-hover'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* ═══════════════ GENERAL TAB ═══════════════ */}
      {activeTab === 'general' && (
        <div className="space-y-5">
          {/* Whisper */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Cpu className="text-blue-500" size={18} />
              Transcription (Whisper)
            </h2>
            <div className="space-y-3">
              <SettingRow label="Provider" value={settings?.whisper_mode === 'api' ? 'Groq API (cloud)' : 'Local model'} />
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
                <span className="text-gray-400 text-sm">Model</span>
                <select
                  value={whisperModel}
                  onChange={e => setWhisperModel(e.target.value)}
                  className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent w-full sm:w-auto"
                >
                  {WHISPER_MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-500">
                {WHISPER_MODELS.find(m => m.value === whisperModel)?.description || 'Select a model'}
              </p>
            </div>
          </section>

          {/* LLM */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <MessageSquare className="text-purple-500" size={18} />
              LLM Configuration
            </h2>
            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
                <span className="text-gray-400 text-sm">Model</span>
                <select
                  value={llmModel}
                  onChange={e => setLlmModel(e.target.value)}
                  className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 focus:border-transparent w-full sm:w-auto sm:max-w-[220px] truncate"
                >
                  {LLM_MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          {/* Daemon */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Clock className="text-green-500" size={18} />
              Daemon
            </h2>
            <SettingRow
              label="Check Interval"
              value={settings ? (settings.check_interval >= 86400 ? `${Math.round(settings.check_interval / 86400)} day(s)` : settings.check_interval >= 3600 ? `${Math.round(settings.check_interval / 3600)} hour(s)` : `${Math.floor(settings.check_interval / 60)} minutes`) : '-'}
            />
          </section>

          {/* Save */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={saveSettings}
              disabled={saving}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save Settings
            </button>
            {saveResult && (
              <span className={`text-sm ${saveResult.includes('Failed') ? 'text-red-400' : 'text-green-400'}`}>
                {saveResult}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ═══════════════ ACCOUNTS TAB ═══════════════ */}
      {activeTab === 'accounts' && (
        <div className="p-5 bg-dark-surface border border-dark-border rounded-xl space-y-5">
          {/* Platform pill tabs */}
          <div className="flex gap-1 p-1 bg-dark-hover rounded-lg">
            {PLATFORMS.map(p => {
              const loggedIn = cookies.find(c => c.platform === p)?.has_cookie
              return (
                <button
                  key={p}
                  onClick={() => handleSwitchPlatform(p)}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm rounded-md transition-colors ${
                    activePlatform === p
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-dark-border'
                  }`}
                >
                  {platformLabel(p)}
                  {loggedIn && <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />}
                </button>
              )
            })}
          </div>

          {/* ── Platform login sections ── */}
          {(() => {
            const name = platformLabel(activePlatform)
            const hasQr = activePlatform === 'bilibili' || activePlatform === 'douyin'
            const isYT = activePlatform === 'youtube'

            if (isYT) {
              const ytLoggedIn = cookies.find(c => c.platform === 'youtube')?.has_cookie
              return <YouTubeLoginSection
                loggedIn={!!ytLoggedIn}
                cookieLoading={cookieLoading}
                cookieMessage={cookieMessage}
                setCookieMessage={setCookieMessage}
                selectedBrowser={selectedBrowser}
                setSelectedBrowser={setSelectedBrowser}
                browsers={BROWSERS}
                handleAutoImport={() => handleAutoImport('youtube')}
                onCookiesSaved={async () => {
                  const data = await fetchAllCookies()
                  setCookies(data.cookies)
                }}
                handleCookieFileUpload={(f: File) => handleCookieFileUpload('youtube', f)}
              />
            }

            return (
              <div className="space-y-4">
                {/* ─── Method 1: Auto-import from browser ─── */}
                <div className="space-y-3">
                  <p className="text-sm text-gray-300 font-medium flex items-center gap-2">
                    <Chrome size={15} className="text-blue-400" />
                    Auto-import from browser
                  </p>
                  <p className="text-xs text-gray-500">
                    Reads cookies directly from your browser — no extensions, no manual steps.
                    {hasQr ? ' Or use QR code below.' : ''}
                  </p>
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedBrowser}
                      onChange={e => setSelectedBrowser(e.target.value)}
                      className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500"
                    >
                      {BROWSERS.map(b => (
                        <option key={b.value} value={b.value}>{b.label}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleAutoImport(activePlatform)}
                      disabled={cookieLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors font-medium disabled:opacity-50"
                    >
                      {cookieLoading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                      {cookieLoading ? 'Importing...' : `Import ${name} Cookies`}
                    </button>
                  </div>
                  <p className="text-xs text-gray-600">
                    Make sure you are logged in to {name} in your browser first. A system permission dialog may appear.
                  </p>
                </div>

                {/* Status message */}
                {cookieMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    cookieMessage.includes('✅') ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                      : cookieMessage.includes('❌') ? 'bg-red-500/10 border border-red-500/30 text-red-400'
                      : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
                  }`}>
                    {cookieMessage}
                  </div>
                )}

                {/* ─── Method 2: QR Code (BiliBili / Douyin only) ─── */}
                {hasQr && (
                  <div className="border-t border-dark-border pt-4 space-y-3">
                    <p className="text-sm text-gray-300 font-medium flex items-center gap-2">
                      <Smartphone size={15} className="text-pink-400" />
                      Or scan QR code with {name} app
                    </p>

                    {qrStatus === 'idle' || qrStatus === 'error' || qrStatus === 'expired' ? (
                      <div>
                        <button
                          onClick={() => startQrLogin(activePlatform as 'bilibili' | 'douyin')}
                          className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors"
                        >
                          <Smartphone size={16} />
                          Generate QR Code
                        </button>
                        {(qrStatus === 'error' || qrStatus === 'expired') && qrMessage && (
                          <p className={`text-sm mt-2 ${qrStatus === 'expired' ? 'text-amber-400' : 'text-red-400'}`}>{qrMessage}</p>
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
                          onClick={() => startQrLogin(activePlatform as 'bilibili' | 'douyin')}
                          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                        >
                          Re-login
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex flex-col items-center gap-3 p-4 bg-white rounded-xl w-fit mx-auto">
                          <QRCodeSVG value={qrUrl} size={180} level="M" />
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
                                {qrMessage || 'Waiting for scan...'}
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
                            onClick={() => startQrLogin(activePlatform as 'bilibili' | 'douyin')}
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
                )}

                {/* ─── Method 3: Upload cookies.txt file (fallback) ─── */}
                <div className={`${hasQr || showFileUpload ? 'border-t border-dark-border pt-4' : ''} space-y-3`}>
                  <button
                    onClick={() => setShowFileUpload(!showFileUpload)}
                    className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    <FileText size={12} />
                    {showFileUpload ? '▾ Hide file upload' : '▸ Or upload cookies.txt file'}
                  </button>
                  {showFileUpload && (
                    <div className="space-y-3 pl-1">
                      <p className="text-xs text-gray-500">
                        Export cookies using a browser extension like{' '}
                        <a
                          href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-0.5"
                        >
                          Get cookies.txt LOCALLY <ExternalLink size={10} />
                        </a>
                        , then upload the file.
                      </p>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".txt,.cookie,.cookies"
                        className="hidden"
                        onChange={e => {
                          const f = e.target.files?.[0]
                          if (f) handleCookieFileUpload(activePlatform, f)
                        }}
                      />
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={cookieLoading}
                        className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                      >
                        {cookieLoading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                        Upload cookies.txt
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })()}

          {/* Status summary */}
          <div className="pt-4 border-t border-dark-border">
            <div className="grid grid-cols-2 gap-2">
              {PLATFORMS.map(p => {
                const info = cookies.find(c => c.platform === p)
                return (
                  <div key={p} className="flex items-center justify-between p-2.5 bg-dark-hover rounded-lg text-sm">
                    <span className="text-white">{platformLabel(p)}</span>
                    <span className={`text-xs ${info?.has_cookie ? 'text-green-400' : 'text-gray-500'}`}>
                      {info?.has_cookie ? 'Logged in' : 'Not set'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════ TOOLS & DATA TAB ═══════════════ */}
      {activeTab === 'tools' && (
        <div className="space-y-5">
          {/* Video Tools Health */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Activity className="text-emerald-500" size={18} />
              Video Tools Health
            </h2>
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
              className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50 mb-3"
            >
              {checkingHealth ? <Loader2 size={16} className="animate-spin" /> : <Activity size={16} />}
              Check Health
            </button>
            {sysHealth && (
              <div className="space-y-2">
                {(['ffmpeg', 'ytdlp'] as const).map(tool => {
                  const info = sysHealth[tool]
                  return (
                    <div key={tool} className={`p-3 rounded-lg flex items-center gap-3 ${
                      info.available ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
                    }`}>
                      <span className={info.available ? 'text-green-400' : 'text-red-400'}>
                        {info.available ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
                      </span>
                      <div>
                        <p className={`text-sm font-medium ${info.available ? 'text-green-300' : 'text-red-300'}`}>
                          {tool === 'ytdlp' ? 'yt-dlp' : 'FFmpeg'}
                        </p>
                        <p className="text-xs text-gray-400">
                          {info.available ? (tool === 'ytdlp' ? `v${info.version}` : info.version) : info.error}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          {/* Data Maintenance */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Trash2 className="text-red-500" size={18} />
              Data Maintenance
            </h2>
            <p className="text-sm text-gray-400 mb-3">
              Check for truncated transcripts (duration &lt; 85% of expected).
            </p>
            <div className="flex gap-3 mb-3">
              <button
                onClick={checkTruncated}
                disabled={checking}
                className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {checking ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                Check for Truncated
              </button>
              {truncatedItems.length > 0 && (
                <button
                  onClick={cleanupTruncated}
                  disabled={cleaning}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {cleaning ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  Delete {truncatedItems.length} Truncated
                </button>
              )}
            </div>
            {cleanupResult && (
              <div className={`p-3 rounded-lg mb-3 ${
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
              <div className="space-y-2 max-h-48 overflow-y-auto">
                <p className="text-sm text-yellow-400 flex items-center gap-2 mb-2">
                  <AlertTriangle size={16} />
                  Found {truncatedItems.length} truncated transcripts:
                </p>
                {truncatedItems.map(item => (
                  <div key={item.episode_id} className="p-3 bg-dark-hover rounded-lg text-sm">
                    <p className="text-white font-medium truncate">{item.episode_title}</p>
                    <p className="text-gray-400 mt-1">
                      Transcript: {formatDuration(item.transcript_duration)} / Expected: {formatDuration(item.episode_duration)}
                      <span className="text-red-400 ml-2">({item.percentage}%)</span>
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Import Subscriptions */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Download className="text-cyan-500" size={18} />
              Import Xiaoyuzhou Subscriptions
            </h2>
            <p className="text-sm text-gray-400 mb-3">
              Import podcasts from Xiaoyuzhou (小宇宙). <span className="text-yellow-400">Profile must be public.</span>
            </p>
            <div className="flex gap-3 mb-3">
              <input
                type="text"
                value={importUsername}
                onChange={e => setImportUsername(e.target.value)}
                placeholder="Username or profile URL"
                className="flex-1 bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                onKeyDown={e => e.key === 'Enter' && !importing && handleImportSubscriptions()}
              />
              <button
                onClick={handleImportSubscriptions}
                disabled={importing || !importUsername.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {importing ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                Import
              </button>
            </div>
            {importError && (
              <div className="p-3 rounded-lg mb-3 bg-red-500/10 border border-red-500/30 text-red-300">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={16} />
                    {importError}
                  </div>
                  <button onClick={() => { setImportResult(null); setImportError(null) }} className="text-red-400 hover:text-red-300">
                    <X size={16} />
                  </button>
                </div>
              </div>
            )}
            {importResult && (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-300">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={16} />
                      Import Complete
                    </div>
                    <button onClick={() => { setImportResult(null); setImportError(null) }} className="text-green-400 hover:text-green-300">
                      <X size={16} />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                    <div><span className="text-gray-400">Found:</span> <span className="text-white font-medium">{importResult.total_found}</span></div>
                    <div><span className="text-gray-400">Added:</span> <span className="text-green-400 font-medium">{importResult.newly_added}</span></div>
                    <div><span className="text-gray-400">Existing:</span> <span className="text-yellow-400 font-medium">{importResult.already_subscribed}</span></div>
                    {importResult.failed > 0 && (
                      <div><span className="text-gray-400">Failed:</span> <span className="text-red-400 font-medium">{importResult.failed}</span></div>
                    )}
                  </div>
                </div>
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
            <p className="text-xs text-gray-500 mt-3">
              Find your username in your profile URL (xiaoyuzhoufm.com/user/<span className="text-cyan-400">username</span>)
            </p>
          </section>
        </div>
      )}
    </div>
  )
}

function YouTubeLoginSection({
  loggedIn, cookieLoading, cookieMessage, setCookieMessage,
  selectedBrowser, setSelectedBrowser,
  browsers, handleAutoImport, onCookiesSaved, handleCookieFileUpload,
}: {
  loggedIn: boolean
  cookieLoading: boolean
  cookieMessage: string
  setCookieMessage: (v: string) => void
  selectedBrowser: string
  setSelectedBrowser: (v: string) => void
  browsers: { value: string; label: string }[]
  handleAutoImport: () => void
  onCookiesSaved: () => Promise<void>
  handleCookieFileUpload: (f: File) => void
}) {
  const [ytMethod, setYtMethod] = useState<'paste' | 'file' | 'browser'>('paste')
  const [pasteValue, setPasteValue] = useState('')
  const [pasteSaving, setPasteSaving] = useState(false)
  const localFileRef = useRef<HTMLInputElement>(null)

  const handlePasteSave = async () => {
    if (!pasteValue.trim()) return
    setPasteSaving(true)
    setCookieMessage('')
    try {
      const text = pasteValue.trim()
      const isNetscape = text.includes('\t') && (text.includes('.youtube.com') || text.includes('#HttpOnly_'))
      if (isNetscape) {
        const blob = new Blob([text], { type: 'text/plain' })
        const file = new File([blob], 'youtube_cookies.txt', { type: 'text/plain' })
        const result = await uploadCookieFile('youtube', file)
        setCookieMessage(`✅ ${result.message}`)
      } else {
        const result = await saveSimpleCookie('youtube', text)
        setCookieMessage(`✅ ${result.message}`)
      }
      await onCookiesSaved()
      setPasteValue('')
    } catch (err) {
      setCookieMessage(`❌ ${err instanceof Error ? err.message : 'Save failed'}`)
    } finally {
      setPasteSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Status */}
      {loggedIn ? (
        <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
          <CheckCircle size={16} className="text-green-400" />
          <span className="text-sm text-green-400">YouTube cookies are set</span>
        </div>
      ) : (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="text-xs text-gray-300">
              <p className="font-medium text-amber-300">YouTube cookies recommended</p>
              <p className="mt-0.5 text-gray-400">
                YouTube may block requests from servers. Upload cookies to ensure all videos work.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Method tabs */}
      <div className="flex gap-1 p-0.5 bg-dark-hover rounded-lg">
        {([
          { id: 'paste' as const, label: 'Paste Cookies', icon: <FileText size={13} /> },
          { id: 'file' as const, label: 'Upload File', icon: <Upload size={13} /> },
          { id: 'browser' as const, label: 'From Browser', icon: <Chrome size={13} /> },
        ]).map(m => (
          <button
            key={m.id}
            onClick={() => setYtMethod(m.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs rounded-md transition-colors ${
              ytMethod === m.id
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {m.icon}
            {m.label}
          </button>
        ))}
      </div>

      {/* Method: Paste */}
      {ytMethod === 'paste' && (
        <div className="space-y-3">
          <div className="p-3 bg-dark-hover/50 rounded-lg space-y-2">
            <p className="text-xs text-gray-300 font-medium">How to get your cookies:</p>
            <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
              <li>Open <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">YouTube</a> in your browser and make sure you're logged in</li>
              <li>Press <kbd className="px-1.5 py-0.5 bg-gray-700 rounded text-[11px] text-white">F12</kbd> to open DevTools</li>
              <li>Go to <strong className="text-white">Console</strong> tab, paste this and press Enter:</li>
            </ol>
            <div className="relative">
              <pre className="p-2 bg-gray-800 rounded text-[11px] text-green-300 font-mono overflow-x-auto select-all">document.cookie</pre>
              <button
                onClick={() => navigator.clipboard.writeText('document.cookie')}
                className="absolute top-1 right-1 p-1 text-gray-500 hover:text-white transition-colors"
                title="Copy command"
              >
                <Download size={12} />
              </button>
            </div>
            <p className="text-[11px] text-gray-500">
              Copy the result (the long string with <code className="text-gray-400">key=value; key=value</code> format) and paste below.
              Alternatively, paste a Netscape cookies.txt content — both formats work.
            </p>
          </div>

          <textarea
            value={pasteValue}
            onChange={e => setPasteValue(e.target.value)}
            placeholder="Paste cookie string or cookies.txt content here..."
            rows={4}
            className="w-full px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 font-mono resize-none"
          />

          <button
            onClick={handlePasteSave}
            disabled={pasteSaving || !pasteValue.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {pasteSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Cookies
          </button>
        </div>
      )}

      {/* Method: File upload */}
      {ytMethod === 'file' && (
        <div className="space-y-3">
          <div className="p-3 bg-dark-hover/50 rounded-lg space-y-2">
            <p className="text-xs text-gray-300 font-medium">Export cookies.txt file:</p>
            <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
              <li>
                Install{' '}
                <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">
                  Get cookies.txt LOCALLY <ExternalLink size={10} className="inline" />
                </a>{' '}
                extension
              </li>
              <li>Open <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">YouTube</a> and log in</li>
              <li>Click the extension icon → Export</li>
              <li>Upload the downloaded file below</li>
            </ol>
          </div>

          <input
            ref={localFileRef}
            type="file"
            accept=".txt,.cookie,.cookies"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0]
              if (f) handleCookieFileUpload(f)
              if (localFileRef.current) localFileRef.current.value = ''
            }}
          />
          <button
            onClick={() => localFileRef.current?.click()}
            disabled={cookieLoading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {cookieLoading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            Upload cookies.txt
          </button>
        </div>
      )}

      {/* Method: From browser */}
      {ytMethod === 'browser' && (
        <div className="space-y-3">
          <div className="p-3 bg-dark-hover/50 rounded-lg">
            <p className="text-xs text-gray-400">
              Reads cookies directly from your browser. Only works when this app runs on your own computer (not cloud deployment).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedBrowser}
              onChange={e => setSelectedBrowser(e.target.value)}
              className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2"
            >
              {browsers.map(b => (
                <option key={b.value} value={b.value}>{b.label}</option>
              ))}
            </select>
            <button
              onClick={handleAutoImport}
              disabled={cookieLoading}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {cookieLoading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
              {cookieLoading ? 'Importing...' : 'Auto-import'}
            </button>
          </div>
        </div>
      )}

      {/* Status message */}
      {cookieMessage && (
        <div className={`p-2.5 rounded-lg text-xs ${
          cookieMessage.includes('✅') ? 'bg-green-500/10 border border-green-500/30 text-green-400'
            : cookieMessage.includes('❌') ? 'bg-red-500/10 border border-red-500/30 text-red-400'
            : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
        }`}>
          {cookieMessage}
        </div>
      )}
    </div>
  )
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-dark-border last:border-0">
      <span className="text-gray-400 text-sm">{label}</span>
      <span className="text-white font-mono text-sm">{value}</span>
    </div>
  )
}
