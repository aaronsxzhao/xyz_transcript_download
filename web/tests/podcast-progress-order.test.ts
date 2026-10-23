// @vitest-environment jsdom
import {beforeEach, expect, it, vi} from 'vitest'
import {useStore} from '../src/lib/store'
import type {ProcessingJob} from '../src/lib/api'

const job = (status: string, progress: number, revision: number) => ({
  job_id: 'podcast', status, progress, revision, message: status,
} as ProcessingJob & {revision: number})
beforeEach(() => useStore.getState().reset())

it('does not let an older list response overwrite a websocket completion', () => {
  useStore.getState().updateJob(job('completed', 100, 5))
  useStore.getState().mergeJobs([job('transcribing', 45, 3)])
  expect(useStore.getState().jobs[0]).toMatchObject({status:'completed', progress:100, revision:5})
})

it('rejects out-of-order individual updates without freezing real later updates', () => {
  useStore.getState().updateJob(job('summarizing', 90, 4))
  useStore.getState().updateJob(job('transcribing', 20, 2))
  expect(useStore.getState().jobs[0].progress).toBe(90)
  useStore.getState().mergeJobs([job('failed', 0, 5)])
  expect(useStore.getState().jobs[0]).toMatchObject({status:'failed', progress:0, revision:5})
})

it('keeps episode identity when a status snapshot omits it', () => {
  useStore.getState().updateJob({...job('transcribing', 40, 1), episode_id:'episode', episode_title:'Podcast title'})
  useStore.getState().mergeJobs([job('summarizing', 80, 2)])
  expect(useStore.getState().jobs[0]).toMatchObject({episode_id:'episode', episode_title:'Podcast title', revision:2})
})

it('accepts a legacy snapshot before versioned updates arrive', () => {
  const legacy = {job_id:'podcast', status:'pending', progress:0, message:'Queued'}
  useStore.getState().mergeJobs([legacy])
  useStore.getState().updateJob(job('transcribing', 30, 1))
  useStore.getState().mergeJobs([legacy])
  expect(useStore.getState().jobs[0]).toMatchObject({status:'transcribing', progress:30, revision:1})
})

it('starts a retried job with its own revision instead of the failed job revision', async () => {
  vi.resetModules()
  vi.doMock('../src/lib/api', () => ({retryJob:vi.fn().mockResolvedValue({new_job_id:'new'}), fetchJob:vi.fn().mockImplementation(() => new Promise(() => {}))}))
  try {
    const {useStore: store} = await import('../src/lib/store')
    const {retryTask} = await import('../src/lib/taskActions')
    await retryTask(job('failed', 0, 30), 'podcast')
    const fresh = store.getState().jobs.find(row => row.job_id === 'new')
    expect(fresh).toMatchObject({status:'pending', revision:0})
    store.getState().mergeJobs([{...job('transcribing', 25, 1), job_id:'new'}])
    expect(store.getState().jobs.find(row => row.job_id === 'new')).toMatchObject({status:'transcribing', revision:1})
  } finally {
    vi.doUnmock('../src/lib/api')
    vi.resetModules()
  }
})
