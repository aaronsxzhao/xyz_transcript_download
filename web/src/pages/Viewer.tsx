import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { 
  ArrowLeft, 
  FileText, 
  MessageSquare, 
  Tag, 
  CheckCircle, 
  Quote,
  ChevronDown,
  ChevronUp,
  Loader2,
  ExternalLink,
} from 'lucide-react'
import { fetchSummary, fetchTranscript, type Summary, type Transcript } from '../lib/api'

type Tab = 'summary' | 'transcript'

export default function Viewer() {
  const { eid } = useParams<{ eid: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('summary')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set())
  
  useEffect(() => {
    if (eid) loadData()
  }, [eid])
  
  async function loadData() {
    setLoading(true)
    try {
      const [summaryData, transcriptData] = await Promise.allSettled([
        fetchSummary(eid!),
        fetchTranscript(eid!),
      ])
      
      if (summaryData.status === 'fulfilled') {
        setSummary(summaryData.value)
        // Expand first topic by default
        if (summaryData.value.topics.length > 0) {
          setExpandedTopics(new Set([summaryData.value.topics[0]]))
        }
      }
      if (transcriptData.status === 'fulfilled') {
        setTranscript(transcriptData.value)
      }
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }
  
  function toggleTopic(topic: string) {
    const newExpanded = new Set(expandedTopics)
    if (newExpanded.has(topic)) {
      newExpanded.delete(topic)
    } else {
      newExpanded.add(topic)
    }
    setExpandedTopics(newExpanded)
  }
  
  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }
  
  // Group key points by topic
  const keyPointsByTopic = summary?.key_points.reduce((acc, kp) => {
    if (!acc[kp.topic]) acc[kp.topic] = []
    acc[kp.topic].push(kp)
    return acc
  }, {} as Record<string, typeof summary.key_points>) || {}
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link
          to="/"
          className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors mt-1"
        >
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-white mb-2">
            {summary?.title || 'Episode Viewer'}
          </h1>
          <div className="flex items-center gap-4">
            {summary && (
              <>
                <span className="flex items-center gap-1.5 text-sm text-gray-400">
                  <Tag size={14} />
                  {summary.topics.length} topics
                </span>
                <span className="flex items-center gap-1.5 text-sm text-gray-400">
                  <MessageSquare size={14} />
                  {summary.key_points.length} key points
                </span>
              </>
            )}
            {transcript && (
              <span className="flex items-center gap-1.5 text-sm text-gray-400">
                <FileText size={14} />
                {formatTime(transcript.duration)}
              </span>
            )}
          </div>
        </div>
        
        {/* Export buttons */}
        <div className="flex items-center gap-2">
          <a
            href={`/api/summaries/${eid}/html`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover text-sm transition-colors"
          >
            <ExternalLink size={16} />
            HTML
          </a>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="flex gap-2 border-b border-dark-border">
        <button
          onClick={() => setActiveTab('summary')}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors ${
            activeTab === 'summary'
              ? 'border-indigo-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <MessageSquare size={18} />
          Summary
        </button>
        <button
          onClick={() => setActiveTab('transcript')}
          disabled={!transcript}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            activeTab === 'transcript'
              ? 'border-indigo-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <FileText size={18} />
          Transcript
        </button>
      </div>
      
      {/* Content */}
      {activeTab === 'summary' && summary && (
        <div className="space-y-6">
          {/* Overview */}
          <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="text-indigo-500" size={20} />
              Overview
            </h2>
            <p className="text-gray-300 whitespace-pre-line leading-relaxed">
              {summary.overview}
            </p>
          </div>
          
          {/* Topics/Key Points */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <MessageSquare className="text-purple-500" size={20} />
              Key Points by Topic
            </h2>
            
            {Object.entries(keyPointsByTopic).map(([topic, points]) => (
              <div
                key={topic}
                className="bg-dark-surface border border-dark-border rounded-xl overflow-hidden"
              >
                <button
                  onClick={() => toggleTopic(topic)}
                  className="w-full flex items-center justify-between p-4 hover:bg-dark-hover transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Tag className="text-indigo-400" size={18} />
                    <span className="font-medium text-white">{topic}</span>
                    <span className="text-sm text-gray-500">
                      ({points.length} points)
                    </span>
                  </div>
                  {expandedTopics.has(topic) ? (
                    <ChevronUp size={20} className="text-gray-400" />
                  ) : (
                    <ChevronDown size={20} className="text-gray-400" />
                  )}
                </button>
                
                {expandedTopics.has(topic) && (
                  <div className="border-t border-dark-border p-4 space-y-4">
                    {points.map((kp, idx) => (
                      <div key={idx} className="pl-4 border-l-2 border-indigo-500/50">
                        <p className="text-gray-200 mb-2">{kp.summary}</p>
                        {kp.original_quote && (
                          <div className="flex items-start gap-2 p-3 bg-dark-hover rounded-lg">
                            <Quote className="text-gray-500 flex-shrink-0 mt-0.5" size={16} />
                            <p className="text-sm text-gray-400 italic">
                              {kp.original_quote}
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          
          {/* Takeaways */}
          {summary.takeaways.length > 0 && (
            <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle className="text-green-500" size={20} />
                Takeaways
              </h2>
              <ul className="space-y-3">
                {summary.takeaways.map((takeaway, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <CheckCircle className="text-green-500 flex-shrink-0 mt-0.5" size={16} />
                    <span className="text-gray-300">{takeaway}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      
      {activeTab === 'transcript' && transcript && (
        <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <FileText className="text-blue-500" size={20} />
            Full Transcript
          </h2>
          
          {transcript.segments.length > 0 ? (
            <div className="space-y-4 max-h-[600px] overflow-y-auto">
              {transcript.segments.map((seg, idx) => (
                <div key={idx} className="flex gap-4">
                  <span className="text-xs text-gray-500 font-mono w-12 flex-shrink-0 pt-0.5">
                    {formatTime(seg.start)}
                  </span>
                  <p className="text-gray-300">{seg.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-300 whitespace-pre-line leading-relaxed">
              {transcript.text}
            </p>
          )}
        </div>
      )}
      
      {!summary && !transcript && (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <FileText className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No content available</p>
          <p className="text-gray-500">Process this episode to generate transcript and summary</p>
        </div>
      )}
    </div>
  )
}
