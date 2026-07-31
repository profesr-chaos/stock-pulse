import type { Stock } from '@/types/stock';

interface WatchlistWheelProps {
  stocks: Stock[];
  onClick: () => void;
}

/**
 * The add-ticker wheel, in Yahoo Finance's region-dropdown slot.
 *
 * Same job as before — one segment per followed stock, click to edit — but
 * drawn as a bare SVG ring instead of a charting library. Recharts was ~100kB
 * of the old critical path to render eleven equal arcs; a dasharray does it in
 * a dozen lines and nothing else on the page needed the dependency.
 */

const RADIUS = 15.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 1.6;

// Segments read as a set, not a scale, so the ramp only has to stay legible on
// FT paper — hence the muted editorial tones rather than a categorical palette.
const SEGMENT_COLORS = [
  '#0F5499', '#990F3D', '#0D7680', '#996A00',
  '#4B5C6B', '#7D3F8C', '#00875A', '#B34B00',
];

const WatchlistWheel = ({ stocks, onClick }: WatchlistWheelProps) => {
  const count = stocks.length;
  const segment = count > 0 ? CIRCUMFERENCE / count : CIRCUMFERENCE;

  return (
    <button
      type="button"
      onClick={onClick}
      // h-full so the hit area fills the strip rather than the 36px ring, and
      // z-10 because the marquee beside it is translated left by half its own
      // (very wide) width — its box passes under this button even though
      // overflow-hidden clips what you see, which reads as an obscured target.
      className="group relative z-10 flex h-full shrink-0 items-center gap-2 border-r border-rule bg-paper pr-3 md:pr-4"
    >
      <span className="relative block h-9 w-9">
        <svg viewBox="0 0 40 40" className="h-9 w-9 -rotate-90" aria-hidden="true">
          <circle
            cx="20" cy="20" r={RADIUS}
            fill="none" stroke="#E6D9CE" strokeWidth="4"
          />
          {stocks.map((stock, index) => (
            <circle
              key={stock.symbol}
              cx="20" cy="20" r={RADIUS}
              fill="none"
              stroke={SEGMENT_COLORS[index % SEGMENT_COLORS.length]}
              strokeWidth="4"
              strokeDasharray={`${Math.max(segment - GAP, 0.5)} ${CIRCUMFERENCE}`}
              strokeDashoffset={-segment * index}
            />
          ))}
        </svg>
        <span className="absolute inset-0 flex items-center justify-center font-mono text-[11px] font-semibold text-ink-strong">
          {count}
        </span>
      </span>
      <span className="hidden text-xs font-semibold uppercase tracking-wide text-ink group-hover:text-ftblue sm:inline">
        Edit
      </span>
      {/* The accessible name is built from the visible text plus this, rather
          than replacing it with an aria-label. An aria-label would not contain
          the "12" and "Edit" a sighted user reads aloud to a screen-reader
          user, which is the mismatch the rule exists to catch. */}
      <span className="sr-only">
        {count === 1 ? 'stock followed' : 'stocks followed'} — open the watchlist editor
      </span>
    </button>
  );
};

export default WatchlistWheel;
