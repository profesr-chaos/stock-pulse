import type { NewsArticle } from '@/types/stock';

interface HeadlineProps {
  article: NewsArticle;
  onOpen: (article: NewsArticle) => void;
}

/**
 * A headline that opens the article's detail dialog.
 *
 * Deliberately only the text, so callers keep wrapping it in their own heading
 * element — `<h3><Headline/></h3>`. A button cannot legally contain a heading,
 * and inverting that nesting would strip the document outline the sections rely
 * on. The outbound link now lives in the dialog rather than on the headline.
 */
const Headline = ({ article, onOpen }: HeadlineProps) => (
  <button
    type="button"
    onClick={() => onOpen(article)}
    className="text-left hover:underline"
  >
    {article.title}
  </button>
);

export default Headline;
