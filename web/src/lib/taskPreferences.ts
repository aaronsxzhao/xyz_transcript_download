import {getPreference} from "./preferences";
export function dismissedTasks(): string[] {
  try {
    const value = JSON.parse(getPreference("dismissed_tasks") || "[]");
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string").slice(-200)
      : [];
  } catch {
    return [];
  }
}
