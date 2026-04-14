/**
 * Global state management with Zustand
 */
import { create } from 'zustand'
import type { ProcessingJob, VideoTask, VideoUploadProgress } from './api'

const LOCAL_VIDEO_TASK_GRACE_MS = 20000

function isActiveVideoTaskStatus(status: string) {
  return !['success', 'failed', 'cancelled', 'discovered'].includes(status)
}

function normalizeVideoTask(task: VideoTask): VideoTask {
  if (task.message?.startsWith('Upload complete.')) {
    return {
      ...task,
      message: 'Queued for processing...',
    }
  }

  if (task.status === 'pending' && !task.message) {
    return {
      ...task,
      message: 'Queued for processing...',
    }
  }
  return task
}

/** Merge websocket/store snapshot with a server fetch (e.g. list poll). Keeps fresher progress when API lags. */
export function mergeVideoTaskPair(existing: VideoTask | undefined, incoming: VideoTask): VideoTask {
  const normalizedIncoming = normalizeVideoTask(incoming)
  if (!existing) return normalizedIncoming

  const existingUpdatedAt = Date.parse(existing.updated_at || existing.created_at || '') || 0
  const incomingUpdatedAt = Date.parse(normalizedIncoming.updated_at || normalizedIncoming.created_at || '') || 0
  const keepExistingProgress =
    isActiveVideoTaskStatus(existing.status) &&
    incomingUpdatedAt < existingUpdatedAt &&
    (normalizedIncoming.progress ?? 0) < (existing.progress ?? 0)

  return {
    ...existing,
    ...normalizedIncoming,
    title: normalizedIncoming.title || existing.title,
    thumbnail: normalizedIncoming.thumbnail || existing.thumbnail,
    channel: normalizedIncoming.channel || existing.channel,
    channel_url: normalizedIncoming.channel_url || existing.channel_url,
    channel_avatar: normalizedIncoming.channel_avatar || existing.channel_avatar,
    published_at: normalizedIncoming.published_at || existing.published_at,
    created_at: normalizedIncoming.created_at || existing.created_at,
    updated_at: normalizedIncoming.updated_at || existing.updated_at,
    progress: keepExistingProgress ? existing.progress : normalizedIncoming.progress,
    status: keepExistingProgress ? existing.status : normalizedIncoming.status,
    message: keepExistingProgress ? existing.message : normalizedIncoming.message,
    error: normalizedIncoming.error || existing.error,
  }
}

export interface VideoUploadSession extends VideoUploadProgress {
  id: string
  path?: string
  error?: string
  taskId?: string
}

interface AppState {
  // Processing jobs
  jobs: ProcessingJob[]
  setJobs: (jobs: ProcessingJob[]) => void
  mergeJobs: (serverJobs: ProcessingJob[]) => void
  updateJob: (job: ProcessingJob) => void
  removeJob: (jobId: string) => void
  clearCompletedJobs: () => void
  
  // Video tasks
  videoTasks: VideoTask[]
  setVideoTasks: (tasks: VideoTask[]) => void
  mergeVideoTasks: (tasks: VideoTask[]) => void
  updateVideoTask: (task: VideoTask) => void
  removeVideoTask: (taskId: string) => void
  selectedVideoTaskId: string | null
  setSelectedVideoTaskId: (id: string | null) => void

  // Upload sessions
  uploadSessions: VideoUploadSession[]
  upsertUploadSession: (session: VideoUploadSession) => void
  removeUploadSession: (sessionId: string) => void
  
  // WebSocket connection
  wsConnected: boolean
  setWsConnected: (connected: boolean) => void
}

export const useStore = create<AppState>((set) => ({
  // Jobs
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
  mergeJobs: (serverJobs) =>
    set((state) => {
      // Create a map of server jobs by job_id
      const serverJobMap = new Map(serverJobs.map(j => [j.job_id, j]))
      
      // Keep local jobs that are either:
      // 1. Present in server response (will be updated)
      // 2. In pending/active state but not yet on server (recently added locally)
      const localOnlyJobs = state.jobs.filter(localJob => {
        if (serverJobMap.has(localJob.job_id)) {
          return false // Will be handled by server job
        }
        // Keep local pending/active jobs that server doesn't know about yet
        const isActive = !['completed', 'failed', 'cancelled'].includes(localJob.status)
        return isActive
      })
      
      // Merge: server jobs take precedence, then local-only active jobs
      const mergedJobs = [
        ...serverJobs,
        ...localOnlyJobs
      ]
      
      return { jobs: mergedJobs }
    }),
  updateJob: (job) =>
    set((state) => {
      const existingIndex = state.jobs.findIndex((j) => j.job_id === job.job_id)
      if (existingIndex >= 0) {
        // Merge with existing job (preserve fields like episode_title if not in update)
        const newJobs = [...state.jobs]
        const existingJob = newJobs[existingIndex]
        newJobs[existingIndex] = {
          ...existingJob,
          ...job,
          // Preserve episode_title if it was set and new update doesn't have it
          episode_title: job.episode_title || existingJob.episode_title,
          episode_id: job.episode_id || existingJob.episode_id,
        }
        return { jobs: newJobs }
      } else {
        // Add new job
        return { jobs: [job, ...state.jobs] }
      }
    }),
  removeJob: (jobId) =>
    set((state) => ({
      jobs: state.jobs.filter((j) => j.job_id !== jobId),
    })),
  clearCompletedJobs: () =>
    set((state) => ({
      jobs: state.jobs.filter((j) => 
        !['completed', 'failed', 'cancelled'].includes(j.status)
      ),
    })),
  
  // Video tasks
  videoTasks: [],
  setVideoTasks: (tasks) => set({ videoTasks: tasks }),
  mergeVideoTasks: (serverTasks) =>
    set((state) => {
      const hasAnyActiveTasks =
        serverTasks.some(task => isActiveVideoTaskStatus(task.status)) ||
        state.videoTasks.some(task => isActiveVideoTaskStatus(task.status))
      const now = Date.now()

      const mergedById = new Map<string, VideoTask>()
      for (const serverTask of serverTasks) {
        const existing = state.videoTasks.find(task => task.id === serverTask.id)
        mergedById.set(serverTask.id, mergeVideoTaskPair(existing, serverTask))
      }

      if (hasAnyActiveTasks) {
        for (const localTask of state.videoTasks) {
          if (!mergedById.has(localTask.id)) {
            const localUpdatedAt = Date.parse(localTask.updated_at || localTask.created_at || '') || 0
            const isFreshLocalOnlyTask =
              localUpdatedAt > 0 &&
              now - localUpdatedAt <= LOCAL_VIDEO_TASK_GRACE_MS

            if (isFreshLocalOnlyTask) {
              mergedById.set(localTask.id, normalizeVideoTask(localTask))
            }
          }
        }
      }

      const orderedTasks = [
        ...serverTasks.map(task => mergedById.get(task.id) ?? task),
        ...Array.from(mergedById.values()).filter(task => !serverTasks.some(serverTask => serverTask.id === task.id)),
      ]

      return { videoTasks: orderedTasks }
    }),
  updateVideoTask: (task) =>
    set((state) => {
      const normalizedTask = normalizeVideoTask(task)
      const idx = state.videoTasks.findIndex((t) => t.id === normalizedTask.id)
      if (idx >= 0) {
        const newTasks = [...state.videoTasks]
        newTasks[idx] = mergeVideoTaskPair(newTasks[idx], normalizedTask)
        return { videoTasks: newTasks }
      }
      return { videoTasks: [normalizedTask, ...state.videoTasks] }
    }),
  removeVideoTask: (taskId) =>
    set((state) => ({
      videoTasks: state.videoTasks.filter((t) => t.id !== taskId),
    })),
  selectedVideoTaskId: null,
  setSelectedVideoTaskId: (id) => set({ selectedVideoTaskId: id }),

  // Upload sessions
  uploadSessions: [],
  upsertUploadSession: (session) =>
    set((state) => {
      const idx = state.uploadSessions.findIndex((s) => s.id === session.id)
      if (idx >= 0) {
        const next = [...state.uploadSessions]
        next[idx] = { ...next[idx], ...session }
        return { uploadSessions: next }
      }
      return { uploadSessions: [session, ...state.uploadSessions] }
    }),
  removeUploadSession: (sessionId) =>
    set((state) => ({
      uploadSessions: state.uploadSessions.filter((s) => s.id !== sessionId),
    })),
  
  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
}))
