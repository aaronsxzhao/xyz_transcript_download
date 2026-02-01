import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Radio, FileText, MessageSquare, Loader2, Plus, ArrowRight, Bell, RefreshCw, X } from 'lucide-react'
import { fetchStats, fetchSummaries, processEpisode, fetchNewEpisodes, checkPodcastsForUpdates, type Stats, type SummaryListItem, type ProcessingJob, type NewEpisode } from '../lib/api'
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
  const [newEpisodes, setNewEpisodes] = useState<NewEpisode[]>([])
  const [checkingUpdates, setCheckingUpdates] = useState(false)
  const [showNewEpisodes, setShowNewEpisodes] = useState(true)
  
  const { jobs, updateJob } = useStore()
  const { addToast } = useToast()
  
  useEffect(() => {
    loadData()
    loadNewEpisodes()
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
  
  async function loadNewEpisodes() {
    try {
      const data = await fetchNewEpisodes()
      setNewEpisodes(data.episodes || [])
    } catch (err) {
      console.error('Failed to load new episodes:', err)
    }
  }
  
  async function handleCheckUpdates() {
    setCheckingUpdates(true)
    try {
      const result = await checkPodcastsForUpdates()
      if (result.new_episodes > 0) {
        setNewEpisodes(result.episodes)
        setShowNewEpisodes(true)
        addToast({
          type: 'success',
          title: 'New episodes found',
          message: `Found ${result.new_episodes} new episode(s)`,
        })
        // Refresh stats
        loadData()
      } else {
        addToast({
          type: 'info',
          title: 'All caught up',
          message: 'No new episodes from subscribed podcasts',
        })
      }
    } catch (err) {
      console.error('Failed to check for updates:', err)
      addToast({
        type: 'error',
        title: 'Failed to check updates',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setCheckingUpdates(false)
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
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-gray-400">Manage your podcast transcripts and summaries</p>
        </div>
        <button
          onClick={handleCheckUpdates}
          disabled={checkingUpdates}
          className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
          title="Check subscribed podcasts for new episodes"
        >
          <RefreshCw size={16} className={checkingUpdates ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">{checkingUpdates ? 'Checking...' : 'Check Updates'}</span>
        </button>
      </div>
      
      {/* New episodes notification */}
      {showNewEpisodes && newEpisodes.length > 0 && (
        <div className="p-4 bg-indigo-900/30 border border-indigo-500/30 rounded-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Bell className="w-5 h-5 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-white mb-2">
                  {newEpisodes.length} New Episode{newEpisodes.length > 1 ? 's' : ''} Available
                </h3>
                <div className="space-y-1">
                  {newEpisodes.slice(0, 5).map((ep) => (
                    <Link
                      key={ep.eid}
                      to={`/podcasts/${ep.podcast_pid}/episodes`}
                      className="block text-sm text-gray-300 hover:text-indigo-300 transition-colors"
                    >
                      <span className="text-indigo-400">{ep.podcast_title}:</span> {ep.title}
                    </Link>
                  ))}
                  {newEpisodes.length > 5 && (
                    <p className="text-sm text-gray-500">
                      +{newEpisodes.length - 5} more episode(s)
                    </p>
                  )}
                </div>
              </div>
            </div>
            <button
              onClick={() => setShowNewEpisodes(false)}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}
      
      {/* Quick process form */}
      <div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Process</h2>
        <form onSubmit={handleProcess} className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <input
            type="url"
            value={episodeUrl}
            onChange={(e) => setEpisodeUrl(e.target.value)}
            placeholder="Paste episode URL..."
            className="flex-1 px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
          />
          <button
            type="submit"
            disabled={processing || !episodeUrl.trim()}
            className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            {processing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
            Process
          </button>
        </form>
      </div>
      
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
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
    <div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-center gap-3 md:gap-4">
        <div className={`p-2 md:p-3 rounded-lg bg-dark-hover ${color}`}>
          <Icon className="w-5 h-5 md:w-6 md:h-6" />
        </div>
        <div>
          <p className="text-xl md:text-2xl font-bold text-white">{value}</p>
          <p className="text-xs md:text-sm text-gray-400">{label}</p>
        </div>
      </div>
    </div>
  )
}
