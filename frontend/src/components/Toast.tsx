interface ToastProps {
  message: string | null;
  onDismiss: () => void;
}

/**
 * The message `useToast` is currently holding. Nothing but presentation — the
 * timer lives in the hook.
 *
 * `role="status"` and `aria-live="polite"` so the change is announced without
 * stealing focus: this always follows a deliberate click, so interrupting the
 * user to tell them what they just did would be rude to a screen reader too.
 */
const Toast = ({ message, onDismiss }: ToastProps) => {
  if (!message) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex max-w-[min(24rem,calc(100vw-2rem))] items-start gap-3 border border-ink-strong bg-ink-strong px-4 py-3 text-paper"
    >
      <p className="text-sm leading-snug">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-mr-1 shrink-0 px-1 text-paper/70 hover:text-paper"
      >
        ×
      </button>
    </div>
  );
};

export default Toast;
