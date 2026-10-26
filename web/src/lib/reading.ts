import { useEffect, useRef } from "react";
import { getAccountId } from "./preferences";
import { getCache, hydrateCache } from "./cache";

export function useReadingPosition(
  key: string,
  elementId?: string,
  ready = true,
) {
  useEffect(() => {
    if (!ready) return;
    const el = elementId
      ? document.getElementById(elementId)
      : document.querySelector("main");
    if (!el) return;
    const owner = getAccountId();
    const storageKey = `xyz_reading:${owner}:${key}`;
    const saved = (() => {
        try {
          return sessionStorage.getItem(storageKey);
        } catch {
          return null;
        }
      })();
    let target = Math.max(0, Number(saved) || 0),
      position = target;
    // The scroll container survives route changes. Zero is a real saved
    // position, and a new note must not inherit the previous note's offset.
    el.scrollTop = target;
    let active = true,
      interacted = false;
    let restoring = target > 0;
    const restore = () => {
      if (restoring) {
        position = target;
        el.scrollTop = target;
        if (el.scrollTop >= target - 1) restoring = false;
      }
    };
    restore();
    if (saved === null && /^(podcast|video):/.test(key))
      void hydrateCache("reading_history").then(() => {
        if (!active || interacted || owner !== getAccountId()) return;
        const [kind, ...parts] = key.split(":");
        target =
          getCache<{ id: string; kind: string; position?: number }[]>(
            "reading_history",
          )?.find((row) => row.kind === kind && row.id === parts.join(":"))
            ?.position || 0;
        restoring = target > 0;
        restore();
      });
    const observer = new ResizeObserver(restore);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    const stop = () => {
      restoring = false;
      interacted = true;
    };
    const navigate = (event: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) stop();
    };
    const timeout = setTimeout(stop, 5000);
    const save = () => {
      if (owner === getAccountId())
        try {
          sessionStorage.setItem(storageKey, String(position));
        } catch {}
    };
    const scroll = () => {
      if (!restoring) {
        position = el.scrollTop;
        save();
      }
    };
    el.addEventListener("scroll", scroll, { passive: true });
    el.addEventListener("wheel", stop, { passive: true });
    el.addEventListener("touchstart", stop, { passive: true });
    el.addEventListener("pointerdown", stop, { passive: true });
    el.addEventListener("keydown", navigate);
    return () => {
      active = false;
      clearTimeout(timeout);
      save();
      observer.disconnect();
      el.removeEventListener("scroll", scroll);
      el.removeEventListener("wheel", stop);
      el.removeEventListener("touchstart", stop);
      el.removeEventListener("pointerdown", stop);
      el.removeEventListener("keydown", navigate);
    };
  }, [key, elementId, ready]);
}

const dialogs: HTMLElement[] = [];

export function useDialog<T extends HTMLElement = HTMLElement>(open: boolean, close: () => void) {
  const ref = useRef<T>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    dialogs.push(dialog);
    const top = () => dialogs[dialogs.length - 1] === dialog;
    const focusable = () =>
      [...dialog.querySelectorAll<HTMLElement>(
          'button,a[href],input,select,textarea,[tabindex]',
        )].filter((element) => element.tabIndex >= 0 && !element.matches(':disabled') && element.getClientRects().length > 0);
    dialog.tabIndex = -1;
    (focusable()[0] || dialog).focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !top()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
      }
      if (event.key === "Tab") {
        const items = focusable();
        const first = items[0];
        const last = items[items.length - 1];
        const focused = document.activeElement;
        if (!first || !dialog.contains(focused) || focused === dialog || focused === (event.shiftKey ? first : last)) {
          event.preventDefault();
          ((event.shiftKey ? last : first) || dialog).focus();
        }
      }
    };
    document.addEventListener("keydown", keydown, true);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      const restore = top();
      dialogs.splice(dialogs.indexOf(dialog), 1);
      if (restore && previous?.isConnected) previous.focus();
    };
  }, [open]);
  return ref;
}
