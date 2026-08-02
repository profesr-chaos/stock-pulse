import { apiFetch } from './api';

/**
 * The two AI toggles.
 *
 * `llmScraping` / `aiSummaries` are what the user asked for; the two
 * `*Available` style fields are what is actually in effect once the key state
 * is folded in. They diverge whenever there is no usable key, which is the
 * case the UI has to explain rather than showing a dead switch.
 */
export interface AppConfig {
  llmScraping: boolean;
  aiSummaries: boolean;
  keyPresent: boolean;
  keyRejected: boolean;
  scrapingGradesImpact: boolean;
  summariesAvailable: boolean;
}

export type ConfigUpdate = Partial<Pick<AppConfig, 'llmScraping' | 'aiSummaries'>>;

export const getConfig = (): Promise<AppConfig> => apiFetch<AppConfig>('/config');

/** Send only the flag being changed — the backend leaves the other alone. */
export const setConfig = (update: ConfigUpdate): Promise<AppConfig> =>
  apiFetch<AppConfig>('/config', { method: 'PUT', body: update });

/**
 * What to tell the user after a toggle landed.
 *
 * Takes the server's resulting config rather than the click, so the message
 * describes what is true now. The "on but no key" wording exists because that
 * combination otherwise looks like the switch did nothing.
 *
 * Switching scraping off says the news keeps coming, since that is the whole
 * anxiety behind a toggle with "LLM" in the name on a news app.
 */
export const describeChange = (patch: ConfigUpdate, next: AppConfig): string | null => {
  if (patch.llmScraping !== undefined) {
    if (!next.llmScraping) {
      return 'LLM scraping off — news still scrapes, just without impact grading.';
    }
    return next.scrapingGradesImpact
      ? 'LLM scraping on — new articles will be graded for impact.'
      : 'LLM scraping on, but there is no usable DSEEK key yet.';
  }

  if (patch.aiSummaries !== undefined) {
    if (!next.aiSummaries) return 'AI summaries off.';
    return next.summariesAvailable
      ? 'AI summaries on.'
      : 'AI summaries on, but there is no usable DSEEK key yet.';
  }

  return null;
};
