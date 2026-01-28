/**
 * Global state management with Zustand
 */
import { create } from 'zustand'
import type { ProcessingJob } from './api'

interface AppState {
  // Processing jobs
  jobs: ProcessingJob[]
  setJobs: (jobs: ProcessingJob[]) => void
  updateJob: (job: ProcessingJob) => void
  
  // WebSocket connection
  wsConnected: boolean
  setWsConnected: (connected: boolean) => void
  
  // UI state
  sidebarOpen: boolean
  toggleSidebar: () => void
}

export const useStore = create<AppState>((set) => ({
  // Jobs
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
  updateJob: (job) =>
    set((state) => {
      const existingIndex = state.jobs.findIndex((j) => j.job_id === job.job_id)
      if (existingIndex >= 0) {
        // Update existing job
        const newJobs = [...state.jobs]
        newJobs[existingIndex] = job
        return { jobs: newJobs }
      } else {
        // Add new job
        return { jobs: [job, ...state.jobs] }
      }
    }),
  
  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
  
  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}))
