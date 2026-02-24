import { useEffect, useRef } from 'react';

/**
 * Custom hook for polling data at regular intervals
 * @param fn - Async function to call
 * @param interval - Polling interval in milliseconds (default: 5000ms)
 * @param enabled - Whether polling is active (default: true)
 */
export function usePolling(
  fn: () => void | Promise<void>,
  interval: number = 5000,
  enabled: boolean = true
) {
  const timeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    if (!enabled) return;

    const poll = async () => {
      if (!isMountedRef.current) return;

      try {
        await fn();
      } catch (e) {
        // Silently fail polling errors to avoid spamming console
        console.debug('Polling error:', e);
      }

      if (!isMountedRef.current) return;

      if (enabled) {
        timeoutRef.current = window.setTimeout(poll, interval);
      }
    };

    // Initial call
    poll();

    return () => {
      isMountedRef.current = false;
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [fn, interval, enabled]);
}

/**
 * Custom hook for polling only when the tab is visible
 * Prevents unnecessary API calls when tab is in background
 */
export function useVisiblePolling(
  fn: () => void | Promise<void>,
  interval: number = 5000,
  enabled: boolean = true
) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return;

    let timeoutId: number | null = null;

    const poll = async () => {
      if (document.hidden) {
        // If tab is hidden, check again in 1 second
        timeoutId = window.setTimeout(poll, 1000);
        return;
      }

      try {
        await fnRef.current();
      } catch (e) {
        console.debug('Polling error:', e);
      }

      timeoutId = window.setTimeout(poll, interval);
    };

    poll();

    return () => {
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
      }
    };
  }, [interval, enabled]);
}
