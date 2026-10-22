import {
  cancelJob,
  cancelVideoTask,
  deleteJob,
  fetchJob,
  retryJob,
  retryVideoTask,
  type ProcessingJob,
} from "./api";
import { getAccountId, setPreference } from "./preferences";
import { useStore } from "./store";
type Kind = "podcast" | "video";
import { dismissedTasks } from "./taskPreferences";
export { dismissedTasks } from "./taskPreferences";
export async function dismissTask(
  job: ProcessingJob,
  kind: Kind,
  remove = true,
) {
  const owner = getAccountId();
  if (kind === "podcast" && remove) {
    await deleteJob(job.job_id);
    if (owner !== getAccountId()) return;
    useStore.getState().removeJob(job.job_id);
  }
  const next = [
    ...new Set([...dismissedTasks(), kind + ":" + job.job_id]),
  ].slice(-200);
  setPreference("dismissed_tasks", JSON.stringify(next));
  window.dispatchEvent(new Event("xyz:tasks-dismissed"));
}
export async function cancelTask(job: ProcessingJob, kind: Kind) {
  const owner = getAccountId();
  const result = await (kind === "video" ? cancelVideoTask(job.job_id) : cancelJob(job.job_id));
  if (owner !== getAccountId()) return;
  const state = useStore.getState();
  const status = result.status || "cancelling";
  const message = status === "cancelled" ? "Cancelled" : ["success", "completed"].includes(status) ? "Completed" : "Stopping safely…";
  // A websocket completion/removal can arrive before this older HTTP response.
  // Apply the acknowledgement to current state, never to the click's snapshot.
  const terminal = ["success", "completed", "failed", "cancelled"];
  if (kind === "video") {
    const current = state.videoTasks.find(t => t.id === job.job_id);
    if (current && !terminal.includes(current.status)) state.updateVideoTask({...current, status, message});
  } else {
    const current = state.jobs.find(t => t.job_id === job.job_id);
    if (current && !terminal.includes(current.status)) state.updateJob({...current, status, message});
  }
}
export async function retryTask(job: ProcessingJob, kind: Kind) {
  const owner = getAccountId();
  if (kind === "video") {
    await retryVideoTask(job.job_id);
    if (owner !== getAccountId()) return;
    const task = useStore
      .getState()
      .videoTasks.find((t) => t.id === job.job_id);
    if (task)
      useStore.getState().updateVideoTask({
        ...task,
        status: "pending",
        progress: 0,
        error: "",
        message: "Waiting for a processing slot.",
      });
  } else {
    const result = await retryJob(job.job_id);
    if (owner !== getAccountId()) return;
    useStore.getState().updateJob({
      ...job,
      job_id: result.new_job_id,
      status: "pending",
      progress: 0,
      message: "Waiting for a processing slot.",
    });
    await dismissTask(job, kind, false);
    void fetchJob(result.new_job_id)
      .then((current) => {
        if (owner === getAccountId()) useStore.getState().updateJob(current);
      })
      .catch(() => {});
  }
}
