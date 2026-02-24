/**
 * Global state management with Zustand
 */
import { create } from 'zustand'
import type { ProcessingJob, VideoTask } from './api'

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
  updateVideoTask: (task: VideoTask) => void
  removeVideoTask: (taskId: string) => void
  selectedVideoTaskId: string | null
  setSelectedVideoTaskId: (id: string | null) => void
  
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
  updateVideoTask: (task) =>
    set((state) => {
      const idx = state.videoTasks.findIndex((t) => t.id === task.id)
      if (idx >= 0) {
        const newTasks = [...state.videoTasks]
        newTasks[idx] = { ...newTasks[idx], ...task }
        return { videoTasks: newTasks }
      }
      return { videoTasks: [task, ...state.videoTasks] }
    }),
  removeVideoTask: (taskId) =>
    set((state) => ({
      videoTasks: state.videoTasks.filter((t) => t.id !== taskId),
    })),
  selectedVideoTaskId: null,
  setSelectedVideoTaskId: (id) => set({ selectedVideoTaskId: id }),
  
  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
}))
