import { useMoves } from '@/hooks/useMoves';
import { changeClass, formatPercent } from '@/lib/format';

interface TickerTagProps {
  symbol: string;
  /** The article's own move, used when the symbol isn't in the shared map. */
  fallbackMove?: number | null;
  onSelect: (symbol: string) => void;
}

/**
 * The ticker chip under a headline. Clicking it filters the whole feed to that
 * symbol, which is a server-side query — the same as using the quote lookup.
 */
const TickerTag = ({ symbol, fallbackMove, onSelect }: TickerTagProps) => {
  const moves = useMoves();
  const move = moves.get(symbol) ?? fallbackMove ?? null;

  return (
    <button
      type="button"
      onClick={() => onSelect(symbol)}
      className="ft-chip hover:bg-paper-tint transition-colors"
      title={`Filter the feed to ${symbol}`}
    >
      <span className="font-semibold text-ftblue">{symbol}</span>
      {move !== null && (
        <span className={changeClass(move)}>{formatPercent(move)}</span>
      )}
      {/* Extends the accessible name instead of replacing it: an aria-label
          of "Filter the feed to AAPL" would not contain the button's visible
          text, which is exactly the mismatch screen-reader users trip over
          when they speak what they see. */}
      <span className="sr-only">— filter the feed to this ticker</span>
    </button>
  );
};

export default TickerTag;
