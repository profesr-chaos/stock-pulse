import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AppConfig } from '@/services/configApi';

import AiSettingsDialog from './AiSettingsDialog';

const CONFIG: AppConfig = {
  llmScraping: true,
  aiSummaries: true,
  keyPresent: true,
  keyRejected: false,
  scrapingGradesImpact: true,
  summariesAvailable: true,
};

const show = (overrides: Partial<AppConfig> = {}, config: AppConfig | null = CONFIG) => {
  const onToggle = vi.fn();
  render(
    <AiSettingsDialog
      open
      onOpenChange={vi.fn()}
      config={config ? { ...config, ...overrides } : undefined}
      saving={false}
      onToggle={onToggle}
      toast={null}
      onDismissToast={vi.fn()}
    />,
  );
  return { onToggle };
};

const scrapingBox = () => screen.getByRole('checkbox', { name: /grade new articles/i });
const summariesBox = () => screen.getByRole('checkbox', { name: /ai summaries on demand/i });

describe('AiSettingsDialog', () => {
  it('reflects the server state', () => {
    show({ llmScraping: false });
    expect(scrapingBox()).not.toBeChecked();
    expect(summariesBox()).toBeChecked();
  });

  it('switching scraping off sends only that flag', () => {
    const { onToggle } = show();
    fireEvent.click(scrapingBox());
    // Not { llmScraping: false, aiSummaries: true } — sending both would let a
    // stale render clobber the other flag.
    expect(onToggle).toHaveBeenCalledWith({ llmScraping: false });
  });

  it('switching summaries off sends only that flag', () => {
    const { onToggle } = show();
    fireEvent.click(summariesBox());
    expect(onToggle).toHaveBeenCalledWith({ aiSummaries: false });
  });

  it('switching scraping back on sends true', () => {
    const { onToggle } = show({ llmScraping: false });
    fireEvent.click(scrapingBox());
    expect(onToggle).toHaveBeenCalledWith({ llmScraping: true });
  });

  it('says scraping carries on without the LLM', () => {
    show();
    expect(screen.getByText(/scraping carries on exactly as before/i)).toBeInTheDocument();
  });

  it('explains a missing key rather than showing a dead switch', () => {
    show({ keyPresent: false, scrapingGradesImpact: false, summariesAvailable: false });
    expect(screen.getAllByText(/no dseek api key is set/i).length).toBeGreaterThan(0);
  });

  it('explains a rejected key', () => {
    show({ keyRejected: true, scrapingGradesImpact: false, summariesAvailable: false });
    expect(screen.getAllByText(/key was rejected/i).length).toBeGreaterThan(0);
  });

  it('does not nag about the key for a flag that is already off', () => {
    show({ llmScraping: false, keyPresent: false, scrapingGradesImpact: false });
    // Only the summaries row should carry the warning.
    expect(screen.getAllByText(/no dseek api key is set/i)).toHaveLength(1);
  });

  it('waits for the config rather than rendering unchecked boxes', () => {
    show({}, null);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
