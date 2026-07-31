import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import QuoteLookup from './QuoteLookup';

const RESULTS = [
  { symbol: 'NVDA', name: 'Nvidia', exchange: 'NMS' },
  { symbol: 'NVDQ', name: 'T-Rex 2X Inverse Nvidia', exchange: 'NMS' },
];

vi.mock('@/hooks/useStockSearch', () => ({
  useStockSearch: (query: string) => ({
    data: query ? RESULTS : [],
    isFetching: false,
  }),
}));

const open = () => {
  const input = screen.getByRole('combobox');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: 'nvda' } });
  return input;
};

describe('QuoteLookup', () => {
  // Typing is debounced, so every case waits for the list rather than
  // asserting against the frame in which the keystroke landed.
  const withResults = async (filter: string | null = null) => {
    const onSelect = vi.fn();
    render(<QuoteLookup filter={filter} onSelect={onSelect} />);
    const input = open();
    await waitFor(() => expect(screen.getByRole('listbox')).toBeInTheDocument());
    return { input, onSelect };
  };

  it('reports the chosen ticker to the page', async () => {
    const { onSelect } = await withResults();
    fireEvent.click(screen.getByText('NVDA'));
    expect(onSelect).toHaveBeenCalledWith('NVDA');
  });

  it('selects with the keyboard, not just the mouse', async () => {
    const { input, onSelect } = await withResults();
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    // ArrowDown moves off the first option, so this is the second one.
    expect(onSelect).toHaveBeenCalledWith('NVDQ');
  });

  it('wraps the highlight rather than running off the end', async () => {
    const { input, onSelect } = await withResults();
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('NVDQ');
  });

  it('exposes the highlighted option to assistive tech', async () => {
    const { input } = await withResults();
    expect(input).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBe('quote-option-1');
  });

  it('closes on Escape without selecting anything', async () => {
    const { input, onSelect } = await withResults();
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('offers a way back to the unfiltered feed', () => {
    const onSelect = vi.fn();
    render(<QuoteLookup filter="NVDA" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('clear filter'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
