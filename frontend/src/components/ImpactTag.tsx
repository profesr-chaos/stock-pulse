import type { Impact } from '@/types/stock';

interface ImpactTagProps {
  impact: Impact | null | undefined;
}

/**
 * The event layer's verdict on an article, as a pill beside the ticker's price
 * and sentiment.
 *
 * Nothing renders for an unjudged article. Null is the absence of a verdict —
 * the article predates the feature, or the judge could not be reached — and
 * printing "LOW" for it would state a conclusion nobody reached. A judged
 * 'low' is a real answer and does get its pill.
 *
 * The word carries the tier; colour only reinforces it.
 */
const STYLES: Record<Impact, string> = {
  high: 'border-claret text-claret font-semibold',
  medium: 'text-ink',
  low: 'text-ink-muted',
};

const ImpactTag = ({ impact }: ImpactTagProps) => {
  if (!impact) return null;

  return (
    <span className={`ft-chip uppercase tracking-wide ${STYLES[impact]}`}>
      {impact}
      <span className="sr-only"> impact</span>
    </span>
  );
};

export default ImpactTag;
