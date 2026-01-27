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
    set((state) => ({
      jobs: state.jobs.map((j) => (j.job_id === job.job_id ? job : j)),
    })),
  
  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
  
  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}))
