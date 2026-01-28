import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Radio, FileText, MessageSquare, Loader2, Plus, ArrowRight } from 'lucide-react'
import { fetchStats, fetchSummaries, processEpisode, type Stats, type SummaryListItem, type ProcessingJob } from '../lib/api'
import { useStore } from '../lib/store'
import { getCache, setCache, CacheKeys } from '../lib/cache'
import { useToast } from '../components/Toast'
import SummaryCard from '../components/SummaryCard'
import ProcessingProgress from '../components/ProcessingProgress'

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [summaries, setSummaries] = useState<SummaryListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [episodeUrl, setEpisodeUrl] = useState('')
  const [processing, setProcessing] = useState(false)
  
  const { jobs, updateJob } = useStore()
  const { addToast } = useToast()
  
  useEffect(() => {
    loadData()
  }, [])
  
  async function loadData() {
    // Load from cache first for instant display
    const cachedStats = getCache<Stats>(CacheKeys.STATS)
    const cachedSummaries = getCache<SummaryListItem[]>(CacheKeys.SUMMARIES)
    
    if (cachedStats) setStats(cachedStats)
    if (cachedSummaries) setSummaries(cachedSummaries)
    if (cachedStats || cachedSummaries) setLoading(false)
    
    // Then fetch fresh data
    try {
      const [statsData, summariesData] = await Promise.all([
        fetchStats(),
        fetchSummaries(),
      ])
      setStats(statsData)
      setSummaries(summariesData)
      
      // Update cache
      setCache(CacheKeys.STATS, statsData)
      setCache(CacheKeys.SUMMARIES, summariesData)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleProcess(e: React.FormEvent) {
    e.preventDefault()
    if (!episodeUrl.trim()) return
    
    setProcessing(true)
    try {
      const result = await processEpisode(episodeUrl)
      
      // Immediately add job to store for instant UI feedback
      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Starting...',
        episode_id: result.episode_id,
        episode_title: result.episode_title,
      })
      
      setEpisodeUrl('')
      addToast({
        type: 'success',
        title: 'Processing started',
        message: 'Check the processing panel for progress',
      })
    } catch (err) {
      console.error('Failed to start processing:', err)
      addToast({
        type: 'error',
        title: 'Failed to start processing',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setProcessing(false)
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
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
        <p className="text-gray-400">Manage your podcast transcripts and summaries</p>
      </div>
      
      {/* Quick process form */}
      <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Process</h2>
        <form onSubmit={handleProcess} className="flex gap-4">
          <input
            type="url"
            value={episodeUrl}
            onChange={(e) => setEpisodeUrl(e.target.value)}
            placeholder="Paste episode URL (e.g., https://www.xiaoyuzhoufm.com/episode/...)"
            className="flex-1 px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            disabled={processing || !episodeUrl.trim()}
            className="flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            {processing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
            Process
          </button>
        </form>
      </div>
      
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={Radio}
            label="Podcasts"
            value={stats.total_podcasts}
            color="text-indigo-500"
          />
          <StatCard
            icon={FileText}
            label="Episodes"
            value={stats.total_episodes}
            color="text-blue-500"
          />
          <StatCard
            icon={FileText}
            label="Transcripts"
            value={stats.total_transcripts}
            color="text-green-500"
          />
          <StatCard
            icon={MessageSquare}
            label="Summaries"
            value={stats.total_summaries}
            color="text-purple-500"
          />
        </div>
      )}
      
      {/* Processing jobs */}
      {jobs.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Processing Queue</h2>
          <div className="space-y-3">
            {jobs.map((job: ProcessingJob) => (
              <ProcessingProgress key={job.job_id} job={job} />
            ))}
          </div>
        </div>
      )}
      
      {/* Recent summaries */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Recent Summaries</h2>
          <Link 
            to="/podcasts" 
            className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
          >
            View all <ArrowRight size={16} />
          </Link>
        </div>
        
        {summaries.length === 0 ? (
          <div className="p-8 bg-dark-surface border border-dark-border rounded-xl text-center">
            <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400">No summaries yet</p>
            <p className="text-sm text-gray-500">Process an episode to generate summaries</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {summaries.slice(0, 6).map((summary) => (
              <SummaryCard key={summary.episode_id} summary={summary} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ 
  icon: Icon, 
  label, 
  value, 
  color 
}: { 
  icon: typeof Radio
  label: string
  value: number
  color: string
}) {
  return (
    <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-center gap-4">
        <div className={`p-3 rounded-lg bg-dark-hover ${color}`}>
          <Icon size={24} />
        </div>
        <div>
          <p className="text-2xl font-bold text-white">{value}</p>
          <p className="text-sm text-gray-400">{label}</p>
        </div>
      </div>
    </div>
  )
}
