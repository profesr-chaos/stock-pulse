import { useMoves } from '@/hooks/useMoves';
import { useSentiments } from '@/hooks/useSentiments';
import {
  changeClass,
  formatPercent,
  formatSentiment,
  sentimentDotClass,
} from '@/lib/format';

interface TickerTagProps {
  symbol: string;
  /** The article's own move, used when the symbol isn't in the shared map. */
  fallbackMove?: number | null;
  onSelect: (symbol: string) => void;
}

/**
 * The ticker chip under a headline. Clicking it filters the whole feed to that
 * symbol, which is a server-side query — the same as searching for it.
 *
 * Carries the stock's sentiment as well as its price move, so the score is
 * readable at the point the ticker is mentioned rather than only in the rail.
 * It is the *stock's* average, not this article's: the chip labels the ticker,
 * and a per-article score here would show the same ticker three different
 * numbers in one column. The article's own score lives in its detail dialog.
 */
const TickerTag = ({ symbol, fallbackMove, onSelect }: TickerTagProps) => {
  const moves = useMoves();
  const sentiments = useSentiments();
  const move = moves.get(symbol) ?? fallbackMove ?? null;
  const sentiment = sentiments.get(symbol);

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
      {sentiment !== undefined && (
        <span className="inline-flex items-center gap-1 border-l border-rule-light pl-1.5">
          {/* The dot is decorative — the signed number beside it already
              carries the direction, so colour is never the only channel. */}
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${sentimentDotClass(sentiment)}`}
            aria-hidden="true"
          />
          <span className="text-ink-muted">{formatSentiment(sentiment)}</span>
        </span>
      )}
      {/* Extends the accessible name instead of replacing it: an aria-label
          of "Filter the feed to AAPL" would not contain the button's visible
          text, which is exactly the mismatch screen-reader users trip over
          when they speak what they see. */}
      <span className="sr-only">
        {sentiment !== undefined ? ' sentiment — ' : ' — '}filter the feed to this ticker
      </span>
    </button>
  );
};

export default TickerTag;
