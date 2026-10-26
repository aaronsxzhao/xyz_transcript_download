/**
 * Global state management with Zustand
 */
import { create } from 'zustand'
import type { ProcessingJob, VideoTask, VideoUploadProgress } from './api'

const LOCAL_VIDEO_TASK_GRACE_MS = 20000
// Successful deletions must outlive requests/events already in flight. These
// markers belong to the current browser account and clear with its state.
const removedJobIds = new Set<string>()
const removedVideoTaskIds = new Set<string>()

// Channel pages keep their own paginated rows, outside the progress store.
// Apply the same account-session deletion policy before displaying/caching them.
export function filterRemovedVideoTasks(tasks: VideoTask[]): VideoTask[] {
  return tasks.filter(task => !removedVideoTaskIds.has(task.id))
}

function mergeProcessingJobPair(existing: ProcessingJob | undefined, incoming: ProcessingJob): ProcessingJob {
  if (!existing) return incoming
  // HTTP snapshots and websocket events can arrive in either order.
  if ((incoming.revision ?? 0) < (existing.revision ?? 0)) return existing
  return {
    ...existing,
    ...incoming,
    episode_title: incoming.episode_title || existing.episode_title,
    episode_id: incoming.episode_id || existing.episode_id,
  }
}

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
  if(normalizedIncoming.client_pending && !existing.client_pending && existing.status!=='discovered')return existing
  const keepExistingProgress = !existing.client_pending && incomingUpdatedAt < existingUpdatedAt
  const {client_pending:_,...confirmedExisting}=existing

  return {
    ...confirmedExisting,
    ...normalizedIncoming,
    title: normalizedIncoming.title || existing.title,
    thumbnail: normalizedIncoming.thumbnail || existing.thumbnail,
    channel: normalizedIncoming.channel || existing.channel,
    channel_url: normalizedIncoming.channel_url || existing.channel_url,
    channel_avatar: normalizedIncoming.channel_avatar || existing.channel_avatar,
    published_at: normalizedIncoming.published_at || existing.published_at,
    created_at: normalizedIncoming.created_at || existing.created_at,
    updated_at: keepExistingProgress ? existing.updated_at : (normalizedIncoming.updated_at || existing.updated_at),
    progress: keepExistingProgress ? existing.progress : normalizedIncoming.progress,
    status: keepExistingProgress ? existing.status : normalizedIncoming.status,
    message: keepExistingProgress ? existing.message : normalizedIncoming.message,
    error: keepExistingProgress ? existing.error : (normalizedIncoming.error ?? existing.error),
  }
}

export interface VideoUploadSession extends VideoUploadProgress {
  id: string
  path?: string
  error?: string
  taskId?: string
}

interface AppState {
  reset: () => void
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
  reset: () => {
    removedJobIds.clear()
    removedVideoTaskIds.clear()
    set({ jobs: [], videoTasks: [], uploadSessions: [], selectedVideoTaskId: null, wsConnected: false })
  },
  // Jobs
  jobs: [],
  setJobs: (jobs) => set({ jobs: jobs.filter(job => !removedJobIds.has(job.job_id)) }),
  mergeJobs: (serverJobs) =>
    set((state) => {
      const visibleServerJobs = serverJobs.filter(job => !removedJobIds.has(job.job_id))
      // Create a map of server jobs by job_id
      const serverJobMap = new Map(visibleServerJobs.map(j => [j.job_id, j]))
      
      // Keep local jobs that are either:
      // 1. Present in server response (will be updated)
      // 2. In pending/active state but not yet on server (recently added locally)
      const localOnlyJobs = state.jobs.filter(localJob => {
        if (serverJobMap.has(localJob.job_id)) {
          return false // Will be handled by server job
        }
        // Keep local pending/active jobs that server doesn't know about yet
        const isActive = !['completed', 'failed', 'cancelled'].includes(localJob.status)
        const created=localJob.created_at || localJob.started_at || 0
        const age=Date.now()-(typeof created==='number' ? created*1000 : Date.parse(created))
        return isActive && age>=0 && age<LOCAL_VIDEO_TASK_GRACE_MS
      })
      
      const existingById = new Map(state.jobs.map(job => [job.job_id, job]))
      // Compare server versions rather than response arrival order.
      const mergedJobs = [
        ...visibleServerJobs.map(job => mergeProcessingJobPair(existingById.get(job.job_id), job)),
        ...localOnlyJobs
      ]
      
      return { jobs: mergedJobs }
    }),
  updateJob: (job) =>
    set((state) => {
      if (removedJobIds.has(job.job_id)) return state
      const existingIndex = state.jobs.findIndex((j) => j.job_id === job.job_id)
      if (existingIndex >= 0) {
        // Merge with existing job (preserve fields like episode_title if not in update)
        const newJobs = [...state.jobs]
        newJobs[existingIndex] = mergeProcessingJobPair(newJobs[existingIndex], job)
        return { jobs: newJobs }
      } else {
        // Add new job
        return { jobs: [job, ...state.jobs] }
      }
    }),
  removeJob: (jobId) => {
    removedJobIds.add(jobId)
    set((state) => ({
      jobs: state.jobs.filter((j) => j.job_id !== jobId),
    }))
  },
  clearCompletedJobs: () =>
    set((state) => ({
      jobs: state.jobs.filter((j) => 
        !['completed', 'failed', 'cancelled'].includes(j.status)
      ),
    })),
  
  // Video tasks
  videoTasks: [],
  setVideoTasks: (tasks) => set({ videoTasks: filterRemovedVideoTasks(tasks) }),
  mergeVideoTasks: (serverTasks) =>
    set((state) => {
      const visibleServerTasks = filterRemovedVideoTasks(serverTasks)
      const hasAnyActiveTasks =
        visibleServerTasks.some(task => isActiveVideoTaskStatus(task.status)) ||
        state.videoTasks.some(task => isActiveVideoTaskStatus(task.status))
      const now = Date.now()

      const mergedById = new Map<string, VideoTask>()
      for (const serverTask of visibleServerTasks) {
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
        ...visibleServerTasks.map(task => mergedById.get(task.id) ?? task),
        ...Array.from(mergedById.values()).filter(task => !visibleServerTasks.some(serverTask => serverTask.id === task.id)),
      ]

      return { videoTasks: orderedTasks }
    }),
  updateVideoTask: (task) =>
    set((state) => {
      if (removedVideoTaskIds.has(task.id)) return state
      const normalizedTask = normalizeVideoTask(task)
      const idx = state.videoTasks.findIndex((t) => t.id === normalizedTask.id)
      if (idx >= 0) {
        const newTasks = [...state.videoTasks]
        newTasks[idx] = mergeVideoTaskPair(newTasks[idx], normalizedTask)
        return { videoTasks: newTasks }
      }
      return { videoTasks: [normalizedTask, ...state.videoTasks] }
    }),
  removeVideoTask: (taskId) => {
    removedVideoTaskIds.add(taskId)
    set((state) => ({
      videoTasks: state.videoTasks.filter((t) => t.id !== taskId),
    }))
  },
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
