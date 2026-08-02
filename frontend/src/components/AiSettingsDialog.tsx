import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';

import Toast from '@/components/Toast';
import type { AppConfig } from '@/services/configApi';

interface AiSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: AppConfig | undefined;
  saving: boolean;
  onToggle: (patch: Partial<Pick<AppConfig, 'llmScraping' | 'aiSummaries'>>) => void;
  /**
   * Rendered inside this dialog's portal rather than by the page.
   *
   * A modal Radix dialog puts `aria-hidden="true"` on every other body child,
   * which silently neuters an `aria-live` region sitting out there: the toast
   * still appears, and a screen reader never hears it. Since the toggles that
   * raise it live in here, the announcement has to live in here too.
   */
  toast: string | null;
  onDismissToast: () => void;
}

interface RowProps {
  label: string;
  help: string;
  checked: boolean;
  inert: string | null;
  disabled: boolean;
  onChange: (next: boolean) => void;
}

/**
 * A plain checkbox, not a custom switch. It is keyboard-operable, announced
 * correctly and styled by the platform for free; a div with role="switch"
 * would be more code to arrive back where `<input type="checkbox">` starts.
 */
const Row = ({ label, help, checked, inert, disabled, onChange }: RowProps) => (
  <label className="flex cursor-pointer items-start gap-3 border-b border-rule-light py-4 last:border-b-0">
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(event) => onChange(event.target.checked)}
      className="mt-0.5 h-4 w-4 shrink-0 accent-ftblue"
    />
    <span className="min-w-0">
      <span className="block text-sm font-semibold text-ink-strong">{label}</span>
      <span className="ft-meta mt-0.5 block">{help}</span>
      {/* The flag is on but cannot take effect. Saying so is the difference
          between "this switch is broken" and "you need a key". */}
      {inert && <span className="mt-1 block text-xs text-claret">{inert}</span>}
    </span>
  </label>
);

/**
 * The two AI toggles.
 *
 * The point of the first one is that it is not load-bearing: news scraping runs
 * identically with it off, minus the impact tiers. The copy says so, because a
 * toggle called "LLM" next to a news app reads like it turns the news off.
 */
const AiSettingsDialog = ({
  open,
  onOpenChange,
  config,
  saving,
  onToggle,
  toast,
  onDismissToast,
}: AiSettingsDialogProps) => {
  const keyProblem = !config
    ? null
    : !config.keyPresent
      ? 'No DSEEK API key is set, so this does nothing yet.'
      : config.keyRejected
        ? 'The DSEEK key was rejected — fix it and restart the backend.'
        : null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-strong/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col border border-ink-strong bg-paper">
          <div className="flex items-start justify-between gap-3 border-b border-rule px-5 py-4">
            <div>
              <Dialog.Title className="font-serif text-xl font-semibold text-ink-strong">
                AI features
              </Dialog.Title>
              <Dialog.Description className="ft-meta mt-1">
                Both are optional. News scraping never depends on them.
              </Dialog.Description>
            </div>
            <Dialog.Close aria-label="Close" className="p-1 text-ink-muted hover:text-ink-strong">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div className="px-5 py-1">
            {!config ? (
              <p className="ft-meta py-4">Loading…</p>
            ) : (
              <>
                <Row
                  label="Grade new articles during scraping"
                  help="Spends one API call per stock per refresh to tag new articles high, medium or low impact. Turn it off and scraping carries on exactly as before, without the tiers."
                  checked={config.llmScraping}
                  inert={config.llmScraping ? keyProblem : null}
                  disabled={saving}
                  onChange={(next) => onToggle({ llmScraping: next })}
                />
                <Row
                  label="AI summaries on demand"
                  help="The summarise button on an article or a stock. Costs nothing until you click it."
                  checked={config.aiSummaries}
                  inert={config.aiSummaries ? keyProblem : null}
                  disabled={saving}
                  onChange={(next) => onToggle({ aiSummaries: next })}
                />
              </>
            )}
          </div>
        </Dialog.Content>

        {/* Sibling of the content, still inside the portal — so it escapes the
            aria-hidden Radix applies to the rest of the page. */}
        <Toast message={toast} onDismiss={onDismissToast} />
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default AiSettingsDialog;
