import { Search } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

export interface ComboOption {
  value: string;
  label: string;
  /** Secondary text — a company name, an exchange code. */
  hint?: string | null;
}

interface ComboBoxProps {
  label: string;
  placeholder: string;
  query: string;
  onQueryChange: (query: string) => void;
  options: ComboOption[];
  onSelect: (value: string) => void;
  /** Shown in the popup when a non-empty query matched nothing. */
  emptyHint?: string;
  className?: string;
}

/**
 * A text input with a filtered list under it, keyboard-navigable.
 *
 * Deliberately dumb: the caller owns the query string and supplies the options,
 * so the same component backs both a client-side filter over the watchlist and
 * a debounced server search over the whole catalogue. Only the popup mechanics
 * — highlight, wrap, Escape, click-away, and the aria wiring that makes a
 * listbox announce itself — live here.
 *
 * Hand-rolled rather than pulled from cmdk + popover: it is one input and one
 * list, and the two libraries together cost more than the component does.
 */
const ComboBox = ({
  label,
  placeholder,
  query,
  onQueryChange,
  options,
  onSelect,
  emptyHint,
  className = '',
}: ComboBoxProps) => {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => setActive(0), [query]);

  // Click-away. Blur alone would fire before the option's click handler.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const choose = (value: string) => {
    onSelect(value);
    onQueryChange('');
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') return setOpen(false);
    if (!open || options.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(options[active].value);
    }
  };

  const showEmpty = open && query.trim().length > 0 && options.length === 0 && emptyHint;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
        aria-hidden="true"
      />
      <input
        type="text"
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        aria-activedescendant={open && options.length ? `${listId}-option-${active}` : undefined}
        aria-label={label}
        autoComplete="off"
        value={query}
        onChange={(event) => {
          onQueryChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-full border border-rule bg-paper py-1.5 pl-8 pr-3 text-xs text-ink placeholder:text-ink-muted focus:border-ftblue focus:outline-none"
      />

      {open && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-30 max-h-64 overflow-y-auto border border-ink-strong bg-paper"
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option.value)}
              className={`flex cursor-pointer items-baseline gap-2 border-b border-rule-light px-3 py-2 last:border-0 ${
                index === active ? 'bg-paper-tint' : ''
              }`}
            >
              <span className="font-mono text-xs font-semibold text-ftblue">{option.label}</span>
              {option.hint && (
                <span className="truncate text-[11px] text-ink-muted">{option.hint}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {showEmpty && (
        <p className="absolute left-0 right-0 top-full z-30 border border-ink-strong bg-paper px-3 py-2 text-[11px] text-ink-muted">
          {emptyHint}
        </p>
      )}
    </div>
  );
};

export default ComboBox;
