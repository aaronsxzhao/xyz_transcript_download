import {getPreference} from "./preferences";
export function dismissedTasks(): string[] {
  try {
    const value = JSON.parse(getPreference("dismissed_tasks") || "[]");
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string")
      : [];
  } catch {
    return [];
  }
}

/** Active attempts are always visible; persisted acknowledgement owns terminal visibility. */
export function taskVisible(status: string, key: string, saved?: boolean | number | null): boolean {
  if (!["success", "completed", "failed", "cancelled"].includes(status)) return true;
  return saved == null ? !dismissedTasks().includes(key) : !saved;
}
