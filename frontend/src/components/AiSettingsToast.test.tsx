import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useToast } from '@/hooks/useToast';
import { describeChange, type AppConfig, type ConfigUpdate } from '@/services/configApi';

import AiSettingsDialog from './AiSettingsDialog';

/**
 * The click-to-toast path, wired exactly as Home wires it.
 *
 * The pieces are unit-tested apart; this covers the glue between them, which
 * is where "a toggle that silently does nothing" would actually live.
 */
const BASE: AppConfig = {
  llmScraping: true,
  aiSummaries: true,
  keyPresent: true,
  keyRejected: false,
  scrapingGradesImpact: true,
  summariesAvailable: true,
};

const Harness = ({ save }: { save: (patch: ConfigUpdate) => Promise<AppConfig> }) => {
  const [config, setConfig] = useState<AppConfig>(BASE);
  const { message, show, dismiss } = useToast();

  const onToggle = useCallback(
    async (patch: ConfigUpdate) => {
      try {
        const next = await save(patch);
        setConfig(next);
        const text = describeChange(patch, next);
        if (text) show(text);
      } catch {
        show('Could not save that — is the API running?');
      }
    },
    [save, show],
  );

  // Wired the way Home wires it: while the dialog is open it owns the toast,
  // so the aria-live region is inside the portal rather than behind the
  // aria-hidden a modal dialog stamps on the rest of the page.
  return (
    <AiSettingsDialog
      open
      onOpenChange={vi.fn()}
      config={config}
      saving={false}
      onToggle={onToggle}
      toast={message}
      onDismissToast={dismiss}
    />
  );
};

const scrapingBox = () => screen.getByRole('checkbox', { name: /grade new articles/i });
const summariesBox = () => screen.getByRole('checkbox', { name: /ai summaries on demand/i });

describe('setting an AI option raises a toast', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('toasts when LLM scraping is switched off, and says news keeps scraping', async () => {
    const save = vi.fn(async (patch: ConfigUpdate) => ({
      ...BASE,
      ...patch,
      scrapingGradesImpact: false,
    }));
    render(<Harness save={save} />);

    fireEvent.click(scrapingBox());

    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());
    expect(screen.getByRole('status')).toHaveTextContent(/news still scrapes/i);
    expect(save).toHaveBeenCalledWith({ llmScraping: false });
  });

  it('toasts when LLM scraping is switched back on', async () => {
    const save = vi.fn(async (patch: ConfigUpdate) => ({ ...BASE, ...patch }));
    render(<Harness save={save} />);

    fireEvent.click(scrapingBox());            // off
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/news still scrapes/i));

    fireEvent.click(scrapingBox());            // back on
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/graded for impact/i),
    );
  });

  it('toasts when AI summaries is set, separately from scraping', async () => {
    const save = vi.fn(async (patch: ConfigUpdate) => ({ ...BASE, ...patch }));
    render(<Harness save={save} />);

    fireEvent.click(summariesBox());

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('AI summaries off.'));
    expect(save).toHaveBeenCalledWith({ aiSummaries: false });
    // Scraping untouched by the summaries toggle.
    expect(scrapingBox()).toBeChecked();
  });

  it('the toast goes away on its own', async () => {
    const save = vi.fn(async (patch: ConfigUpdate) => ({ ...BASE, ...patch }));
    render(<Harness save={save} />);

    fireEvent.click(summariesBox());
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());

    act(() => void vi.advanceTimersByTime(4000));
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
  });

  it('a failed save says so instead of claiming the change landed', async () => {
    const save = vi.fn(async () => {
      throw new Error('offline');
    });
    render(<Harness save={save} />);

    fireEvent.click(scrapingBox());

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/could not save/i));
    // And the switch snaps back to the server's state rather than lying.
    expect(scrapingBox()).toBeChecked();
  });
});
