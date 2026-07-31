import { useState } from 'react';

interface NewsImageProps {
  src: string | null;
  alt: string;
  className?: string;
  /** The LCP element. Exactly one image on the page should set this. */
  priority?: boolean;
}

/**
 * A publisher's image, or nothing.
 *
 * These are third-party URLs, so we cannot re-encode them to AVIF/WebP or
 * offer a `srcset` — the only levers left on our side are loading priority,
 * off-main-thread decoding, and a reserved box so a late image cannot shift
 * the layout. A dead link renders as absent rather than as a broken icon.
 */
const NewsImage = ({ src, alt, className = '', priority = false }: NewsImageProps) => {
  const [failed, setFailed] = useState(false);

  if (!src || failed) return null;

  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      loading={priority ? 'eager' : 'lazy'}
      decoding={priority ? 'sync' : 'async'}
      // React 18 has no fetchPriority prop; the lowercase attribute passes through.
      {...{ fetchpriority: priority ? 'high' : 'low' }}
      // Publisher CDNs commonly reject hotlinks by Referer, and we owe them no
      // referrer anyway.
      referrerPolicy="no-referrer"
      className={`w-full h-full object-cover bg-paper-tint ${className}`}
    />
  );
};

export default NewsImage;
