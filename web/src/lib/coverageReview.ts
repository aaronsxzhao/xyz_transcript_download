import {authFetch} from './api'

export async function retryCoverageReview(taskId: string): Promise<{ task_id: string }> {
  const res = await authFetch(`/api/video-notes/tasks/${taskId}/review-coverage`, {method:'POST'})
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not start coverage review')
  }
  return res.json()
}
