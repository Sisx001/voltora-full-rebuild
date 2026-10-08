import {useEffect, useRef, useState} from 'react';

export function readPreference(key: string, fallback: string) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

// Do not rewrite persisted values on mount. Malformed or inaccessible storage stays
// untouched until the user actually changes state; storage failures never crash UI.
export function usePersistentState<T>(key: string, initial: () => T, disabled = false, json = true) {
  const [value, setValue] = useState<T>(initial);
  const previous = useRef(value);
  useEffect(() => {
    if (Object.is(previous.current, value)) return;
    previous.current = value;
    if (disabled) return;
    try { localStorage.setItem(key, json ? JSON.stringify(value) : String(value)); } catch { /* Keep in-memory state for this tab. */ }
  }, [key, value, disabled, json]);
  return [value, setValue] as const;
}
