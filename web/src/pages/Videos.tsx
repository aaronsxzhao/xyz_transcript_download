import { useCallback } from 'react'
import VideoNoteForm from '../components/video/VideoNoteForm'
import VideoHistory from '../components/video/VideoHistory'
import MarkdownPreview from '../components/video/MarkdownPreview'
import { useStore } from '../lib/store'
import { fetchVideoTask, type VideoTask } from '../lib/api'

export default function Videos() {
  const { videoTasks, selectedVideoTaskId, setSelectedVideoTaskId, updateVideoTask } = useStore()

  const selectedTask = videoTasks.find(t => t.id === selectedVideoTaskId) || null

  const handleTaskCreated = (taskId: string) => {
    setSelectedVideoTaskId(taskId)
  }

  const handleSelect = useCallback(async (task: VideoTask) => {
    setSelectedVideoTaskId(task.id)
    // Fetch full task data including transcript and versions
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
      {/* Left: Form */}
      <div className="w-80 flex-shrink-0 overflow-y-auto custom-scrollbar bg-dark-surface rounded-xl border border-dark-border p-4">
        <VideoNoteForm onTaskCreated={handleTaskCreated} />
      </div>

      {/* Center: History */}
      <div className="w-64 flex-shrink-0 overflow-hidden bg-dark-surface rounded-xl border border-dark-border p-4">
        <VideoHistory onSelect={handleSelect} />
      </div>

      {/* Right: Preview */}
      <div className="flex-1 min-w-0 overflow-hidden bg-dark-surface rounded-xl border border-dark-border p-4">
        <MarkdownPreview task={selectedTask} />
      </div>
    </div>
  )
}
