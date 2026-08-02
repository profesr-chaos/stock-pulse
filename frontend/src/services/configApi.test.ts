import { describe, expect, it } from 'vitest';

import { describeChange, type AppConfig } from './configApi';

const CONFIG: AppConfig = {
  llmScraping: true,
  aiSummaries: true,
  keyPresent: true,
  keyRejected: false,
  scrapingGradesImpact: true,
  summariesAvailable: true,
};

const after = (overrides: Partial<AppConfig>): AppConfig => ({ ...CONFIG, ...overrides });

describe('describeChange', () => {
  it('reassures that news keeps scraping when the LLM goes off', () => {
    const message = describeChange(
      { llmScraping: false },
      after({ llmScraping: false, scrapingGradesImpact: false }),
    );
    expect(message).toMatch(/news still scrapes/i);
  });

  it('confirms grading when scraping goes on with a usable key', () => {
    expect(describeChange({ llmScraping: true }, after({}))).toMatch(/graded for impact/i);
  });

  it('flags that switching scraping on did nothing without a key', () => {
    const message = describeChange(
      { llmScraping: true },
      after({ keyPresent: false, scrapingGradesImpact: false }),
    );
    expect(message).toMatch(/no usable dseek key/i);
  });

  it('describes the summaries flag on its own', () => {
    expect(describeChange({ aiSummaries: false }, after({ aiSummaries: false })))
      .toBe('AI summaries off.');
    expect(describeChange({ aiSummaries: true }, after({}))).toBe('AI summaries on.');
  });

  it('flags summaries switched on without a usable key', () => {
    const message = describeChange(
      { aiSummaries: true },
      after({ keyRejected: true, summariesAvailable: false }),
    );
    expect(message).toMatch(/no usable dseek key/i);
  });

  it('describes the flag that changed, not the other one', () => {
    // Both are off in the result, but only summaries was touched.
    const message = describeChange(
      { aiSummaries: false },
      after({ llmScraping: false, aiSummaries: false, scrapingGradesImpact: false }),
    );
    expect(message).toBe('AI summaries off.');
  });

  it('has nothing to say about an empty patch', () => {
    expect(describeChange({}, after({}))).toBeNull();
  });
});
