import { useCallback, useState } from 'react'
import VideoNoteForm from '../components/video/VideoNoteForm'
import VideoHistory from '../components/video/VideoHistory'
import MarkdownPreview from '../components/video/MarkdownPreview'
import { useStore } from '../lib/store'
import { fetchVideoTask, type VideoTask } from '../lib/api'
import { Plus, ChevronUp } from 'lucide-react'

export default function Videos() {
  const { videoTasks, selectedVideoTaskId, setSelectedVideoTaskId, updateVideoTask } = useStore()
  const [formOpen, setFormOpen] = useState(false)

  const selectedTask = videoTasks.find(t => t.id === selectedVideoTaskId) || null

  const handleTaskCreated = (taskId: string) => {
    updateVideoTask({
      id: taskId,
      url: '',
      platform: '',
      title: '',
      thumbnail: '',
      status: 'pending',
      progress: 0,
      message: 'Queued for processing...',
      markdown: '',
      transcript: null,
      style: '',
      model: '',
      formats: [],
      quality: '',
      extras: '',
      video_understanding: false,
      video_interval: 4,
      grid_cols: 3,
      grid_rows: 3,
      duration: 0,
      error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    setSelectedVideoTaskId(taskId)
    setFormOpen(false)
  }

  const handleSelect = useCallback(async (task: VideoTask) => {
    setSelectedVideoTaskId(task.id)
    if (task.status === 'success' && !task.markdown) {
      try {
        const full = await fetchVideoTask(task.id)
        updateVideoTask(full)
      } catch (e) {
        console.error('Failed to fetch task details:', e)
      }
    }
  }, [setSelectedVideoTaskId, updateVideoTask])

  return (
    <div className="h-[calc(100vh-2rem)] flex gap-4 p-4">
      {/* Left panel: New button + History (primary) */}
      <div className="w-[380px] flex-shrink-0 flex flex-col min-h-0 gap-3">
        {/* New Note / Drawer toggle */}
        {!formOpen ? (
          <button
            onClick={() => setFormOpen(true)}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-sm transition-colors flex-shrink-0"
          >
            <Plus size={16} />
            New Video Note
          </button>
        ) : (
          <div className="bg-dark-surface rounded-xl border border-dark-border flex-shrink-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-3 pb-0">
              <h3 className="text-sm font-semibold text-white">Generate Video Notes</h3>
              <button
                onClick={() => setFormOpen(false)}
                className="p-1 text-gray-500 hover:text-white transition-colors"
                title="Close"
              >
                <ChevronUp size={16} />
              </button>
            </div>
            <div className="px-4 pb-4 pt-2 max-h-[50vh] overflow-y-auto custom-scrollbar">
              <VideoNoteForm onTaskCreated={handleTaskCreated} hideTitle />
            </div>
          </div>
        )}

        {/* History (takes remaining space) */}
        <div className="flex-1 min-h-0 overflow-hidden bg-dark-surface rounded-xl border border-dark-border p-4">
          <VideoHistory onSelect={handleSelect} />
        </div>
      </div>

      {/* Right: Preview */}
      <div className="flex-1 min-w-0 overflow-hidden bg-dark-surface rounded-xl border border-dark-border p-4">
        <MarkdownPreview task={selectedTask} />
      </div>
    </div>
  )
}
