import { useMemo } from 'react';

const TITLE = 'Stock Pulse';

interface MastheadProps {
  /** Whether the scraper is actually grading articles with the LLM right now. */
  flicker: boolean;
}

/**
 * The masthead, doubling as the LLM-grading indicator.
 *
 * Flickering RGB while the scraper is grading with the LLM, flat black when it
 * is not — an ambient read on whether the app is spending tokens, without a
 * status line taking up masthead space.
 *
 * Driven by the *effective* state, not the toggle: with the flag on but no
 * usable key nothing is being graded, and a flickering title would be claiming
 * otherwise.
 *
 * The randomness is per-letter timing, picked once at mount and then left to
 * CSS (see `.animate-rgb-flicker` in index.css). Re-rolling colours from JS on
 * a timer would re-render the top of the page several times a second forever.
 */
const Masthead = ({ flicker }: MastheadProps) => {
  // Fixed for the life of the component: new offsets on every render would
  // restart each letter's animation and the flicker would freeze.
  const timings = useMemo(
    () =>
      Array.from(TITLE, () => ({
        // Negative delay starts each letter mid-cycle, so they are already out
        // of phase on the first frame rather than flashing in unison once.
        delay: `-${(Math.random() * 2).toFixed(2)}s`,
        duration: `${(0.6 + Math.random() * 0.9).toFixed(2)}s`,
      })),
    [],
  );

  return (
    <span className="shrink-0 border-l border-rule pl-3 font-serif text-base font-bold tracking-tight md:pl-4 md:text-lg">
      {/* The real title, for assistive tech. aria-label on a bare span is not
          reliably announced, and every letter below is hidden — without this
          the masthead would read as empty. */}
      <span className="sr-only">{TITLE}</span>

      {Array.from(TITLE, (letter, index) => (
        <span
          key={index}
          aria-hidden="true"
          // Black is the off state, and also the base the animation paints
          // over — so `prefers-reduced-motion` lands on a legible masthead
          // rather than whichever colour the keyframes happened to start on.
          style={{
            color: '#000000',
            ...(flicker && {
              ['--flicker-delay' as string]: timings[index].delay,
              ['--flicker-duration' as string]: timings[index].duration,
            }),
          }}
          className={flicker ? 'animate-rgb-flicker' : undefined}
        >
          {/* The space is non-breaking so the title never wraps mid-word in a
              cramped masthead. */}
          {letter === ' ' ? ' ' : letter}
        </span>
      ))}
    </span>
  );
};

export default Masthead;
