import { OptionalTool } from '../components/DeferredView'
const PerformancePanel = lazy(() => import('../components/PerformancePanel'))
const CustomModelFields = lazy(() => import('../components/CustomModelFields'))
import type {ConnectionDraft} from '../components/CustomModelFields'
import { useUnsavedChanges } from '../lib/unsavedChanges'
const DataRecovery = lazy(() => import('../components/DataRecovery'))
const TranscriptMaintenance = lazy(() => import('../components/TranscriptMaintenance'))
import { useAuth } from '../contexts/AuthContext'
import { getAccountId, getPreference, setPreference } from '../lib/preferences'
import { CacheKeys, getCache, setCache } from '../lib/cache'
import { usePageTiming } from '../lib/pageTiming'
import LoadError from '../components/LoadError'
import { lazy, useState, useEffect, useRef, useCallback } from 'react'
import {
  Cpu, MessageSquare, Clock, Loader2, CheckCircle, AlertTriangle,
  Save, Download, X, Activity, Smartphone, Chrome,
  ExternalLink, Settings2, UserCircle, Wrench, Upload, FileText, Link, Video,
} from 'lucide-react'
const QRCodeSVG = lazy(() => import('qrcode.react').then(module=>({default:module.QRCodeSVG})))
import {
  fetchSettings, updateSettings, testLlmConnection, importUserSubscriptions,
  ImportSubscriptionsResult, fetchSysHealth, fetchAllCookies, validateBilibiliCookie,
  bilibiliQrGenerate, bilibiliQrPoll, douyinQrGenerate, douyinQrPoll,
  uploadCookieFile, importBrowserCookies, saveSimpleCookie,
  fetchNotionPages, fetchDouyinCookieDiagnosis, DouyinCookieDiagnosis,
} from '../lib/api'
import PlatformIcon, { PLATFORM_COLORS } from '../components/PlatformIcon'

interface SettingsData {
  whisper_mode: string
  whisper_model: string
  whisper_backend: string
  whisper_device: string
  llm_model: string
  llm_provider: 'server' | 'groq' | 'custom'
  transcription_provider: 'server' | 'custom'
  llm_base_url: string
  whisper_base_url: string
  llm_key_saved: boolean
  whisper_key_saved: boolean
  llm_key_error?: string
  whisper_key_error?: string
  groq_available: boolean
  llm_configured: boolean
  whisper_provider: string
  check_interval: number
}


const WHISPER_MODELS = [
  { value: 'whisper-large-v3', label: 'whisper-large-v3', description: 'More accurate, slower' },
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo', description: 'Faster, slightly less accurate' },
]



type TopTab = 'general' | 'accounts' | 'tools'

const TOP_TABS: { id: TopTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: 'General', icon: <Settings2 size={16} /> },
  { id: 'accounts', label: 'Platform Accounts', icon: <UserCircle size={16} /> },
  { id: 'tools', label: 'Tools & Data', icon: <Wrench size={16} /> },
]

export default function Settings() {
  const { authEnabled } = useAuth()
  const [activeTab, setActiveTab] = useState<TopTab>('general')
  const [maintenanceOpened,setMaintenanceOpened] = useState(false)
  const [settings, setSettings] = useState<SettingsData | null>(() => getCache(CacheKeys.SETTINGS))
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)

  const localWhisperModels = ['tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'].map(value => ({ value, label: value, description: 'Local Whisper model' }))
  const whisperModels = settings?.whisper_mode === 'local' ? localWhisperModels : WHISPER_MODELS
  const [whisperModel, setWhisperModel] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmProvider, setLlmProvider] = useState<'server' | 'groq' | 'custom'>('server')
  const [transcriptionProvider,setTranscriptionProvider]=useState<'server'|'custom'>('server')
  const [summaryConnection,setSummaryConnection]=useState<ConnectionDraft>({baseUrl:''})
  const [transcriptionConnection,setTranscriptionConnection]=useState<ConnectionDraft>({baseUrl:''})
  const [testingLlm, setTestingLlm] = useState(false)
  const [llmTestResult, setLlmTestResult] = useState('')
  const [legacyModels,setLegacyModels]=useState([{value:"",label:"Server Default"}])
  const loadLegacyModels=()=>void import('../lib/legacyModelOptions').then(module=>setLegacyModels(module.LLM_MODELS)).catch(()=>{})
  const groqModels = ['openai/gpt-oss-120b', 'openai/gpt-oss-20b']
  const llmModels = llmProvider === 'groq' ? groqModels.map(value => ({ value, label: value })) : legacyModels
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)


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
  const [douyinDiagnosis, setDouyinDiagnosis] = useState<DouyinCookieDiagnosis | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const BROWSERS = [
    { value: 'chrome', label: 'Chrome' },
    { value: 'firefox', label: 'Firefox' },
    { value: 'edge', label: 'Edge' },
    { value: 'safari', label: 'Safari' },
    { value: 'brave', label: 'Brave' },
  ]

  const VIDEO_STYLES = [
    { id: 'minimal', label: '精简 Minimal' },
    { id: 'detailed', label: '详细 Detailed' },
    { id: 'academic', label: '学术 Academic' },
    { id: 'tutorial', label: '教程 Tutorial' },
    { id: 'xiaohongshu', label: '小红书 Social' },
    { id: 'life_journal', label: '生活向 Journal' },
    { id: 'task_oriented', label: '任务导向 Tasks' },
    { id: 'business', label: '商业 Business' },
    { id: 'meeting_minutes', label: '会议纪要 Minutes' },
  ]
  const VIDEO_FORMATS = [
    { id: 'toc', label: 'Table of Contents' },
    { id: 'link', label: 'Timestamp Links' },
    { id: 'screenshot', label: 'Screenshots' },
    { id: 'summary', label: 'AI Summary' },
  ]
  const AUDIO_QUALITIES = [
    { id: 'fast', label: 'Fast (32k)' },
    { id: 'medium', label: 'Medium (64k)' },
    { id: 'slow', label: 'High (128k)' },
  ]
  const VIDEO_QUALITIES = [
    { id: '360', label: '360p' },
    { id: '480', label: '480p' },
    { id: '720', label: '720p' },
    { id: '1080', label: '1080p' },
    { id: 'best', label: 'Best' },
  ]

  const [vdStyle, setVdStyle] = useState(() => getPreference('vd_style') || 'detailed')
  const [vdFormats, setVdFormats] = useState<string[]>(() => {
    try {
      const saved=JSON.parse(getPreference('vd_formats') || 'null')
      return Array.isArray(saved)&&saved.every(value=>typeof value==='string') ? saved : ['toc','summary','screenshot']
    }
    catch { return ['toc', 'summary', 'screenshot'] }
  })
  const [vdQuality, setVdQuality] = useState(() => getPreference('vd_quality') || 'medium')
  const [vdVideoQuality, setVdVideoQuality] = useState(() => getPreference('vd_video_quality') || '720')
  const [savedDraft, setSavedDraft] = useState('')
  const savedVideoDraft = useRef([vdStyle,vdFormats,vdQuality,vdVideoQuality])
  const settingsRequest = useRef(0)
  const settingsWrite = useRef(false)
  const draft = JSON.stringify([whisperModel, llmModel, llmProvider, vdStyle, vdFormats, vdQuality, vdVideoQuality,transcriptionProvider,summaryConnection,transcriptionConnection])
  const dirty = !!savedDraft && draft !== savedDraft
  useUnsavedChanges(dirty)


  const toggleVdFormat = (id: string) => {
    setVdFormats(prev => prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id])
  }

  const [notionKey, setNotionKey] = useState(() => getPreference('notion_api_key') || '')
  const [notionTestResult, setNotionTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [notionTesting, setNotionTesting] = useState(false)

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
    qrAutoRef.current += 1
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
    const autoId = ++qrAutoRef.current

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

      let pollInFlight = false
      qrPollRef.current = setInterval(async () => {
        if (qrAutoRef.current !== autoId || pollInFlight) return
        pollInFlight = true
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
          if(qrAutoRef.current===autoId)setQrMessage(err instanceof Error ? err.message : 'Connection interrupted. Checking again…')
        } finally { pollInFlight = false }
      }, 2000)
    } catch (err) {
      if (qrAutoRef.current === autoId) {
        setQrStatus('error')
        const detail = err instanceof Error ? err.message : ''
        setQrMessage(
          detail || (
            qrRetryCountRef.current > 0
              ? `Failed to generate QR code after ${qrRetryCountRef.current + 1} attempts. ${appName} may be rate-limiting. Wait a moment and try again.`
              : 'Failed to generate QR code. Check your network connection.'
          )
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

  useEffect(() => { void loadSettings(); return () => { settingsRequest.current++ } }, [])

  const [accountValidation,setAccountValidation] = useState<{valid:boolean;reason:string;message:string}|null>(null)
  const [validatingAccount,setValidatingAccount] = useState(false)
  const [accountsLoading,setAccountsLoading] = useState(true)
  const [accountsError,setAccountsError] = useState('')
  const accountsRequest = useRef(0)
  useEffect(()=>setAccountValidation(null),[cookies,activePlatform])
  const loadAccounts = useCallback(async () => {
    const request=++accountsRequest.current, owner=getAccountId()
    setAccountsLoading(true);setAccountsError('')
    try {const data=await fetchAllCookies();if(request===accountsRequest.current&&owner===getAccountId())setCookies(data.cookies)}
    catch {if(request===accountsRequest.current&&owner===getAccountId())setAccountsError('Could not read platform accounts. Connection status is unknown. Retry to check your saved accounts.')}
    finally {if(request===accountsRequest.current&&owner===getAccountId())setAccountsLoading(false)}
  }, [])
  useEffect(() => {
    if (activeTab !== 'accounts') return
    void loadAccounts()
    return()=>{accountsRequest.current++}
  }, [activeTab,loadAccounts])

  useEffect(() => {
    if (activeTab !== 'accounts' || activePlatform !== 'douyin') return
    fetchDouyinCookieDiagnosis()
      .then(setDouyinDiagnosis)
      .catch(() => setDouyinDiagnosis(null))
  }, [activeTab, activePlatform, cookies])

  useEffect(() => {
    if (settings && (!savedDraft || draft === savedDraft)) {
      const savedWhisperModel = settings.whisper_model
      const savedLlmModel = settings.llm_model
      setWhisperModel(savedWhisperModel)
      setLlmModel(savedLlmModel)
      setLlmProvider(settings.llm_provider)
      setTranscriptionProvider(settings.transcription_provider||'server')
      const summaryDraft={baseUrl:settings.llm_base_url||''},transcriptionDraft={baseUrl:settings.whisper_base_url||''}
      setSummaryConnection(summaryDraft);setTranscriptionConnection(transcriptionDraft)
      setSavedDraft(JSON.stringify([savedWhisperModel, savedLlmModel, settings.llm_provider, ...savedVideoDraft.current,settings.transcription_provider||'server',summaryDraft,transcriptionDraft]))
    }
  }, [settings])

  async function loadSettings() {
    if (settingsWrite.current) return
    const request = ++settingsRequest.current
    const owner = getAccountId()
    setLoading(true)
    setLoadError('')
    try {
      const data = await fetchSettings()
      if (owner !== getAccountId() || request !== settingsRequest.current) return
      setSettings(data)
      setCache(CacheKeys.SETTINGS, data, owner)
    } catch (err) {
      if (owner === getAccountId() && request === settingsRequest.current) setLoadError(err instanceof Error ? err.message : 'Cannot load settings. Please retry.')
    } finally {
      if (owner === getAccountId() && request === settingsRequest.current) setLoading(false)
    }
  }

  async function saveSettings() {
    if (!settings || settingsWrite.current) return
    settingsWrite.current=true
    const operation=++settingsRequest.current
    setLoading(false)
    const owner=getAccountId()
    setSaving(true)
    setSaveResult(null)
    try {
      const result=await updateSettings({
        whisper_model: whisperModel,
        llm_model: llmModel,
        llm_provider: llmProvider,
        transcription_provider:transcriptionProvider,
        llm_base_url:summaryConnection.baseUrl,
        whisper_base_url:transcriptionConnection.baseUrl,
        llm_api_key:summaryConnection.apiKey,
        whisper_api_key:transcriptionConnection.apiKey,
      })
      if(owner!==getAccountId())return
      setPreference('whisper_model', whisperModel)
      setPreference('llm_model', llmModel)
      setPreference('vd_style', vdStyle)
      setPreference('vd_formats', JSON.stringify(vdFormats))
      setPreference('vd_quality', vdQuality)
      setPreference('vd_video_quality', vdVideoQuality)
      savedVideoDraft.current=[vdStyle,vdFormats,vdQuality,vdVideoQuality]
      setSavedDraft(draft)
      if(result.settings){setSettings(result.settings);setCache(CacheKeys.SETTINGS,result.settings,owner)}
      setLoadError('')
      setSaveResult('Submitted settings saved.')
      setTimeout(() => { if (operation===settingsRequest.current && owner===getAccountId()) setSaveResult(null) }, 3000)
    } catch (err) {
      console.error('Failed to save settings:', err)
      if (owner===getAccountId()) setSaveResult('Failed to save settings: ' + (err instanceof Error ? err.message : 'Please retry'))
    } finally {
      settingsWrite.current=false
      if (owner===getAccountId()) setSaving(false)
    }
  }

  async function verifyAndSaveLlm() {
    if (!settings || settingsWrite.current) return
    settingsWrite.current=true
    settingsRequest.current++
    setLoading(false)
    setSaveResult(null)
    const owner=getAccountId()
    setTestingLlm(true)
    setLlmTestResult('')
    try {
      const result = await testLlmConnection({ llm_provider: llmProvider, llm_model: llmModel })
      if(owner!==getAccountId())return
      const saved = await updateSettings({ llm_provider: llmProvider, llm_model: result.model })
      if(owner!==getAccountId())return
      setLlmModel(current => current === llmModel ? result.model : current)
      setSavedDraft(previous => { if (!previous) return previous; const values = JSON.parse(previous); values[1] = result.model; values[2] = llmProvider; return JSON.stringify(values) })
      setPreference('llm_model', result.model)
      const confirmed=saved.settings || {...settings,llm_provider:llmProvider,llm_model:result.model}
      setSettings(confirmed);setCache(CacheKeys.SETTINGS,confirmed,owner)
      setLoadError('')
      setLlmTestResult('Connected and saved. Podcast and video summaries are ready.')
    } catch (error) {
      if (owner===getAccountId()) setLlmTestResult(error instanceof Error ? error.message : 'Could not connect to the summary provider')
    } finally { settingsWrite.current=false; if (owner===getAccountId()) setTestingLlm(false) }
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

  usePageTiming('settings', !!settings, CacheKeys.SETTINGS, !!loadError)

  const platformLabel = (p: string) =>
    p === 'bilibili' ? 'BiliBili' : p === 'youtube' ? 'YouTube' : p.charAt(0).toUpperCase() + p.slice(1)

  return (
    <div className="settings-page min-w-0 mx-auto">
      <div className="mb-5">
        <h1 className="page-title text-2xl font-bold text-white mb-1">Settings</h1>
        <p className="text-sm text-gray-500">Configure AI models, platform logins, and system tools</p>
      </div>

      {loading && <p role="status" className="text-sm text-gray-400 mb-4 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />{settings ? 'Refreshing settings…' : 'Loading account settings…'}</p>}
      {loadError && <LoadError message={loadError} onRetry={() => void loadSettings()} />}

          {/* Save */}
          <div className="sticky top-0 z-20 flex flex-wrap items-center gap-3 p-3 bg-dark-bg border border-dark-border rounded-xl settings-savebar mb-4">
            <span role="status" className="text-sm text-gray-400">{!settings ? 'Settings not loaded' : dirty ? 'Unsaved changes' : 'All changes saved'}</span>
            <button
              onClick={saveSettings}
              disabled={!settings || saving || testingLlm || !dirty}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {saving ? 'Saving…' : 'Save Settings'}
            </button>
            {saveResult && (
              <span className={`text-sm ${saveResult.includes('Failed') ? 'text-red-400' : 'text-green-400'}`}>
                {saveResult}
              </span>
            )}
          </div>

      {/* Top-level tab bar */}
      <div className="grid grid-cols-3 gap-1 p-1 bg-dark-surface border border-dark-border rounded-xl mb-5">
        {TOP_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => {setActiveTab(tab.id);if(tab.id==='tools')setMaintenanceOpened(true)}}
            className={`min-w-0 flex flex-col sm:flex-row items-center justify-center gap-2 px-2 py-2.5 text-sm font-medium rounded-lg transition-colors ${
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
              <label className="flex flex-wrap items-center justify-between gap-2 text-sm">Transcription provider<select aria-label="Transcription provider" disabled={!settings||saving} value={transcriptionProvider} onChange={e=>{const provider=e.target.value as 'server'|'custom';setTranscriptionProvider(provider);setWhisperModel(provider==='custom'?'':whisperModels[0].value)}} className="bg-dark-hover border border-dark-border rounded-lg px-3 py-2"><option value="server">Server configured transcription</option><option value="custom">My OpenAI-compatible service</option></select></label>
              {transcriptionProvider==='custom'?<OptionalTool fallback={<p role="status">Loading model settings…</p>}><CustomModelFields kind="transcription" value={transcriptionConnection} model={whisperModel} keySaved={!!settings?.whisper_key_saved} savedBase={settings?.whisper_base_url||''} keyError={settings?.whisper_key_error} checkingSaved={loading} onChange={setTranscriptionConnection} onModel={setWhisperModel} disabled={!settings||saving}/></OptionalTool>:<>
              <SettingRow label="Server provider" value={!settings ? 'Loading…' : settings.whisper_mode === 'api' ? `${settings.whisper_provider || 'Configured'} API` : 'Local model'} />
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
                <span className="text-gray-400 text-sm">Model</span>
                <select
                  aria-label="Transcription model" disabled={!settings}
                  value={whisperModel}
                  onChange={e => setWhisperModel(e.target.value)}
                  className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent w-full sm:w-auto"
                >
                  {whisperModels.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-500">
                {whisperModels.find(m => m.value === whisperModel)?.description || 'Select a model'}
              </p></>}
              {settings?.whisper_key_saved&&<button type="button" disabled={saving} className="text-sm text-gray-400 underline" onClick={()=>{setTranscriptionProvider('server');setWhisperModel(whisperModels[0].value);setTranscriptionConnection(value=>({...value,apiKey:''}))}}>Remove saved transcription key on save</button>}
              {settings?.whisper_key_error&&<p role="alert" className="text-sm text-amber-300">{settings.whisper_key_error}</p>}
            </div>
          </section>

          {/* LLM */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <MessageSquare className="text-purple-500" size={18} />
              LLM Configuration
            </h2>
            <div className="space-y-3">
              <label className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-sm text-gray-400">
                Summary provider
                <select aria-label="Summary provider" disabled={!settings || testingLlm || saving} value={llmProvider} onChange={e => {
                  const provider = e.target.value as 'server' | 'groq' | 'custom'
                  setLlmProvider(provider)
                  setLlmModel(provider === 'custom' ? '' : provider === 'groq' ? groqModels[0] : settings?.llm_provider==='server'?settings.llm_model:'')
                  setLlmTestResult('')
                }} className="bg-dark-hover border border-dark-border text-white rounded-lg px-3 py-2">
                  <option value="groq" disabled={!settings?.groq_available}>Groq — reuse transcription API key</option>
                  <option value="server">Server configured provider</option>
                  <option value="custom">My OpenAI-compatible service</option>
                </select>
              </label>
              <p className="text-xs text-gray-400">{llmProvider === 'groq'
                ? 'Groq generates summaries with the existing transcription key and your current Groq plan. No OpenAI API account is needed.'
                : llmProvider === 'custom'
                  ? 'Summaries use your Base URL, API key, and selected model. Refresh models to see this endpoint’s model list.'
                  : 'Summaries use the provider configured on the server.'} Video frame analysis requires a vision-capable provider.</p>
              {llmProvider==='custom'?<OptionalTool fallback={<p role="status">Loading model settings…</p>}><CustomModelFields kind="summary" value={summaryConnection} model={llmModel} keySaved={!!settings?.llm_key_saved} savedBase={settings?.llm_base_url||''} keyError={settings?.llm_key_error} checkingSaved={loading} onChange={setSummaryConnection} onModel={setLlmModel} disabled={!settings||saving}/></OptionalTool>:<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-dark-border">
                <span className="text-gray-400 text-sm">Model</span>
                <select
                  aria-label="Summary model"
                  onFocus={loadLegacyModels} onPointerEnter={loadLegacyModels}
                  disabled={!settings || testingLlm || saving}
                  value={llmModel}
                  onChange={e => { setLlmModel(e.target.value); setLlmTestResult('') }}
                  className="bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 focus:border-transparent w-full sm:w-auto sm:max-w-[220px] truncate"
                >
                  {!llmModels.some(m => m.value === llmModel) && <option value={llmModel}>{llmModel || 'Server default'}</option>}
                  {llmModels.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>}
              {settings?.llm_key_saved&&<button type="button" disabled={saving} className="block text-sm text-gray-400 underline" onClick={()=>{setLlmProvider('server');setLlmModel('');setSummaryConnection(value=>({...value,apiKey:''}))}}>Remove saved summary key on save</button>}
              {settings?.llm_key_error&&<p role="alert" className="text-sm text-amber-300">{settings.llm_key_error}</p>}
              {llmProvider!=='custom'&&<button onClick={verifyAndSaveLlm} disabled={!settings || saving || testingLlm || (llmProvider === 'groq' && !settings?.groq_available)} className="px-4 py-2 bg-indigo-600 text-white rounded-lg disabled:opacity-50 flex items-center gap-2">
                {testingLlm && <Loader2 size={16} className="animate-spin" />} Test and save summaries
              </button>}
              {llmTestResult && <p role="status" className="text-sm text-gray-300">{llmTestResult}</p>}
            </div>
          </section>

          {/* Daemon */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Clock className="text-green-500" size={18} />
              Automatic checks
            </h2>
            <SettingRow
              label="Check Interval"
              value={settings ? (settings.check_interval >= 86400 ? `${Math.round(settings.check_interval / 86400)} day(s)` : settings.check_interval >= 3600 ? `${Math.round(settings.check_interval / 3600)} hour(s)` : `${Math.floor(settings.check_interval / 60)} minutes`) : '-'}
            />
          </section>

          {/* Notion */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Link className="text-orange-500" size={18} />
              Notion Export
            </h2>
            <div className="space-y-3">
              <div className="flex flex-col gap-2">
                <label className="text-gray-400 text-sm">Integration Token</label>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="password"
                    value={notionKey}
                    onChange={e => {
                      setNotionKey(e.target.value)
                      setNotionTestResult(null)
                    }}
                    placeholder="ntn_..."
                    className="flex-1 bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-orange-500 focus:border-transparent font-mono"
                  />
                  <button
                    aria-label="Save Notion integration token"
                    onClick={() => {
                      setPreference('notion_api_key', notionKey.trim())
                      setNotionTestResult(null)
                    }}
                    className="px-3 py-2 bg-dark-hover hover:bg-dark-border text-white text-sm rounded-lg transition-colors"
                  >
                    <Save size={14} />
                  </button>
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!notionKey.trim()) {
                    setNotionTestResult({ ok: false, message: 'Enter a Notion API key first' })
                    return
                  }
                  setPreference('notion_api_key', notionKey.trim())
                  setNotionTesting(true)
                  setNotionTestResult(null)
                  try {
                    const data = await fetchNotionPages()
                    setNotionTestResult({
                      ok: true,
                      message: `Connected! Found ${data.pages.length} accessible page${data.pages.length !== 1 ? 's' : ''}.`,
                    })
                  } catch (err) {
                    setNotionTestResult({
                      ok: false,
                      message: err instanceof Error ? err.message : 'Connection failed',
                    })
                  } finally {
                    setNotionTesting(false)
                  }
                }}
                disabled={notionTesting || !notionKey.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors text-sm disabled:opacity-50"
              >
                {notionTesting ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
                Test Connection
              </button>
              {notionTestResult && (
                <div className={`p-2.5 rounded-lg text-xs ${
                  notionTestResult.ok
                    ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                    : 'bg-red-500/10 border border-red-500/30 text-red-400'
                }`}>
                  {notionTestResult.ok ? <CheckCircle size={12} className="inline mr-1.5" /> : <AlertTriangle size={12} className="inline mr-1.5" />}
                  {notionTestResult.message}
                </div>
              )}
              <div className="p-3 bg-dark-hover/50 rounded-lg space-y-1.5">
                <p className="text-xs text-gray-300 font-medium">Setup instructions:</p>
                <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
                  <li>
                    Go to{' '}
                    <a href="https://www.notion.so/profile/integrations" target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:text-orange-300">
                      Notion Integrations <ExternalLink size={10} className="inline" />
                    </a>
                    {' '}and create an integration
                  </li>
                  <li>Copy the Internal Integration Secret and paste it above</li>
                  <li>In Notion, open the page you want to export to, click <strong className="text-white">...</strong> &gt; <strong className="text-white">Connect to</strong> &gt; select your integration</li>
                </ol>
              </div>
            </div>
          </section>

          {/* Video Defaults */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-1 flex items-center gap-2">
              <Video className="text-cyan-500" size={18} />
              Video Processing Defaults
            </h2>
            <p className="text-xs text-gray-500 mb-4">Applied when processing discovered videos from channel updates</p>

            <div className="space-y-4">
              <div>
                <span className="text-gray-400 text-sm block mb-2">Note Style</span>
                <div className="flex flex-wrap gap-1.5">
                  {VIDEO_STYLES.map(s => (
                    <button
                      key={s.id}
                      aria-pressed={vdStyle===s.id}
                      onClick={() => setVdStyle(s.id)}
                      className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                        vdStyle === s.id
                          ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                          : 'bg-dark-hover text-gray-400 border border-transparent hover:text-white'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-gray-400 text-sm block mb-2">Included Sections</span>
                <div className="flex flex-wrap gap-1.5">
                  {VIDEO_FORMATS.map(f => (
                    <button
                      key={f.id}
                      aria-pressed={vdFormats.includes(f.id)}
                      onClick={() => toggleVdFormat(f.id)}
                      className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                        vdFormats.includes(f.id)
                          ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                          : 'bg-dark-hover text-gray-400 border border-transparent hover:text-white'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1">
                  <span className="text-gray-400 text-sm block mb-2">Audio Quality</span>
                  <div className="flex flex-wrap gap-1.5">
                    {AUDIO_QUALITIES.map(q => (
                      <button
                        key={q.id}
                        aria-pressed={vdQuality===q.id}
                        onClick={() => setVdQuality(q.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                          vdQuality === q.id
                            ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                            : 'bg-dark-hover text-gray-400 border border-transparent hover:text-white'
                        }`}
                      >
                        {q.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex-1">
                  <span className="text-gray-400 text-sm block mb-2">Video Quality</span>
                  <div className="flex flex-wrap gap-1.5">
                    {VIDEO_QUALITIES.map(q => (
                      <button
                        key={q.id}
                        aria-pressed={vdVideoQuality===q.id}
                        onClick={() => setVdVideoQuality(q.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                          vdVideoQuality === q.id
                            ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                            : 'bg-dark-hover text-gray-400 border border-transparent hover:text-white'
                        }`}
                      >
                        {q.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </section>


        </div>
      )}

      {/* ═══════════════ ACCOUNTS TAB ═══════════════ */}
      {activeTab === 'accounts' && (
        <div className="p-5 bg-dark-surface border border-dark-border rounded-xl space-y-5">
          {/* Platform pill tabs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 p-1 bg-dark-hover rounded-lg">
            {PLATFORMS.map(p => {
              const loggedIn = cookies.find(c => c.platform === p)?.has_cookie
              return (
                <button
                  key={p}
                  onClick={() => handleSwitchPlatform(p)}
                  aria-pressed={activePlatform === p}
                  className={`min-w-0 flex items-center justify-center gap-1.5 px-3 py-2 text-sm rounded-md transition-colors ${
                    activePlatform === p
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-dark-border'
                  }`}
                >
                  <PlatformIcon platform={p} size={15} className={activePlatform === p ? 'text-white' : PLATFORM_COLORS[p] || 'text-gray-400'} />
                  <span className="min-w-0 break-words">{platformLabel(p)}</span>
                  {loggedIn && <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />}
                </button>
              )
            })}
          </div>

          {accountsLoading && <p role="status">Loading platform accounts…</p>}
          {accountsError && <div role="alert"><p>{accountsError}</p><button onClick={()=>void loadAccounts()}>Retry accounts</button></div>}
          {!accountsLoading && !accountsError && activePlatform==='bilibili' && cookies.some(c=>c.platform==='bilibili'&&c.has_cookie) && <div className="space-y-2 text-sm"><button disabled={validatingAccount} onClick={async()=>{const owner=getAccountId();setValidatingAccount(true);try{const result=await validateBilibiliCookie();if(owner===getAccountId())setAccountValidation(result)}catch{setAccountValidation({valid:false,reason:'error',message:'Could not verify connection. Retry.'})}finally{setValidatingAccount(false)}}}>{validatingAccount?'Checking connection…':'Check connection'}</button>{accountValidation&&<p role="status">{accountValidation.valid?'Connection verified.':accountValidation.reason==='expired'?'Connection expired. Sign in again below.':accountValidation.message}</p>}</div>}
          {/* ── Platform login sections ── */}
          {(() => {
            if(accountsLoading || accountsError) return null
            const name = platformLabel(activePlatform)
            const hasQr = activePlatform === 'bilibili' || activePlatform === 'douyin'
            const isYT = activePlatform === 'youtube'

            if (isYT) {
              const ytLoggedIn = cookies.find(c => c.platform === 'youtube')?.has_cookie
              return <YouTubeLoginSection
                cloud={authEnabled}
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

            const platformLoggedIn = cookies.find(c => c.platform === activePlatform)?.has_cookie

            return (
              <div className="space-y-4">
                {platformLoggedIn && (
                  <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                    <CheckCircle size={16} className="text-green-400" />
                    <span className="text-sm text-green-400">{name} connection saved</span>
                  </div>
                )}

                {activePlatform === 'douyin' && (
                  <>
                    <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
                        <div className="space-y-1">
                          <p className="text-sm text-amber-300 font-medium">QR login is unreliable right now</p>
                          <p className="text-xs text-amber-200/80">
                            Use browser cookie import for best results. If yt-dlp is blocked, localhost now tries a Chromium fallback.
                          </p>
                        </div>
                      </div>
                    </div>
                    {douyinDiagnosis && (
                      <div className={`p-3 rounded-lg border ${
                        douyinDiagnosis.looks_usable
                          ? 'bg-cyan-500/10 border-cyan-500/30'
                          : 'bg-red-500/10 border-red-500/30'
                      }`}>
                        <div className="flex items-start gap-2">
                          {douyinDiagnosis.looks_usable ? (
                            <CheckCircle size={16} className="text-cyan-400 mt-0.5 flex-shrink-0" />
                          ) : (
                            <AlertTriangle size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
                          )}
                          <div className="space-y-2">
                            <p className={`text-sm ${douyinDiagnosis.looks_usable ? 'text-cyan-300' : 'text-red-300'}`}>
                              {douyinDiagnosis.message}
                            </p>
                            <p className="text-xs text-gray-400">
                              Saved {douyinDiagnosis.cookie_count} cookies across {douyinDiagnosis.domains.length} domains.
                            </p>
                            {douyinDiagnosis.present.length > 0 && (
                              <p className="text-xs text-gray-300">
                                Present: {douyinDiagnosis.present.join(', ')}
                              </p>
                            )}
                            {douyinDiagnosis.missing.length > 0 && (
                              <p className="text-xs text-gray-400">
                                Missing: {douyinDiagnosis.missing.join(', ')}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* ─── Method 1: Auto-import from browser ─── */}
                {!authEnabled && <div className="space-y-3">
                  <p className="text-sm text-gray-300 font-medium flex items-center gap-2">
                    <Chrome size={15} className="text-blue-400" />
                    Auto-import from browser
                  </p>
                  <p className="text-xs text-gray-500">
                    Reads cookies directly from your browser — no extensions, no manual steps.
                    {hasQr ? ' Or use QR code below.' : ''}
                  </p>
                  <div className="flex items-center gap-2">
                    <select aria-label="Browser for local cookie import"
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
                </div>}

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
                          <OptionalTool fallback={<p>Loading QR code…</p>}><QRCodeSVG value={qrUrl} size={180} level="M" /></OptionalTool>
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
                  <div key={p} data-account-status className="min-w-0 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:justify-between p-2.5 bg-dark-hover rounded-lg text-sm">
                    <span className="min-w-0 flex items-center gap-2 text-white">
                      <PlatformIcon platform={p} size={14} className={PLATFORM_COLORS[p] || 'text-gray-400'} />
                      {platformLabel(p)}
                    </span>
                    <span className={`min-w-0 break-words text-xs ${info?.has_cookie ? 'text-green-400' : 'text-gray-500'}`}>
                      {accountsLoading?'Loading…':accountsError?'Unknown':info?.has_cookie ? 'Saved · not verified' : 'Not connected'}
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
          <OptionalTool fallback={<p role="status">Loading performance tools…</p>}><PerformancePanel /></OptionalTool>
          <OptionalTool fallback={<p>Loading recovery tools…</p>}><DataRecovery /></OptionalTool>
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


          {/* Import Subscriptions */}
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Download className="text-cyan-500" size={18} />
              Import Xiaoyuzhou Subscriptions
            </h2>
            <p className="text-sm text-gray-400 mb-3">
              Import podcasts from Xiaoyuzhou (小宇宙). <span className="text-yellow-400">Profile must be public.</span>
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mb-3">
              <input
                type="text"
                value={importUsername}
                onChange={e => setImportUsername(e.target.value)}
                placeholder="Username or profile URL"
                className="min-w-0 flex-1 bg-dark-hover border border-dark-border text-white text-sm rounded-lg px-3 py-2 focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
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
      {maintenanceOpened && <div hidden={activeTab!=='tools'} className="mt-5">
        <OptionalTool fallback={<p role="status">Loading maintenance tools…</p>}><TranscriptMaintenance/></OptionalTool>
      </div>}
    </div>
  )
}

function YouTubeLoginSection({
  cloud, loggedIn, cookieLoading, cookieMessage, setCookieMessage,
  selectedBrowser, setSelectedBrowser,
  browsers, handleAutoImport, onCookiesSaved, handleCookieFileUpload,
}: {
  cloud: boolean
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
  const [ytMethod, setYtMethod] = useState<'paste' | 'file' | 'browser'>('file')
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
          <span className="text-sm text-green-400">YouTube connection saved — verified when a video is accessed</span>
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
        ]).filter(m => !cloud || m.id !== 'browser').map(m => (
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
              <li>Open <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">YouTube</a> in your browser and make sure you're logged in</li>
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
              <li>Open <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">YouTube</a> and log in</li>
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
            <select aria-label="Browser for local cookie import"
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
