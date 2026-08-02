import { useCallback, useEffect, useRef, useState } from 'react';

const DISMISS_AFTER = 3200;

/**
 * One transient message at a time.
 *
 * No toast library: the whole requirement is "say what just changed, then go
 * away", which is a string and a timer. sonner/react-hot-toast would add a
 * dependency and a portal to render a div this app already knows how to style.
 *
 * A second call replaces the first rather than stacking. Toggling twice quickly
 * should leave the latest state on screen, not a pile to read in order.
 */
export const useToast = () => {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number>();

  const show = useCallback((next: string) => {
    window.clearTimeout(timer.current);
    setMessage(next);
    timer.current = window.setTimeout(() => setMessage(null), DISMISS_AFTER);
  }, []);

  // A pending timer holding a setState after unmount is a leak and a warning.
  useEffect(() => () => window.clearTimeout(timer.current), []);

  return { message, show, dismiss: useCallback(() => setMessage(null), []) };
};
