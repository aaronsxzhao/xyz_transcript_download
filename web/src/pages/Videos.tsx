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
      {/* Left panel: Form + History stacked */}
      <div className="w-[380px] flex-shrink-0 flex flex-col gap-4 min-h-0">
        <div className="overflow-y-auto custom-scrollbar bg-dark-surface rounded-xl border border-dark-border p-5">
          <VideoNoteForm onTaskCreated={handleTaskCreated} />
        </div>
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
