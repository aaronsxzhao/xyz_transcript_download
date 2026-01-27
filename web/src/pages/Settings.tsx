import { useState, useEffect } from 'react'
import { Cpu, MessageSquare, Clock, Loader2, CheckCircle } from 'lucide-react'
import { fetchSettings } from '../lib/api'

interface SettingsData {
  whisper_mode: string
  whisper_model: string
  whisper_backend: string
  whisper_device: string
  llm_model: string
  check_interval: number
}

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  
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
