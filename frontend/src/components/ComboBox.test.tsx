import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ComboBox, { type ComboOption } from './ComboBox';

const OPTIONS: ComboOption[] = [
  { value: 'NVDA', label: 'NVDA', hint: 'Nvidia' },
  { value: 'MSFT', label: 'MSFT', hint: 'Microsoft' },
];

const setup = (options = OPTIONS, query = 'n') => {
  const onSelect = vi.fn();
  const onQueryChange = vi.fn();
  render(
    <ComboBox
      label="Pick a ticker"
      placeholder="Ticker…"
      query={query}
      onQueryChange={onQueryChange}
      options={options}
      onSelect={onSelect}
      emptyHint="Nothing matches that."
    />,
  );
  const input = screen.getByRole('combobox', { name: 'Pick a ticker' });
  fireEvent.focus(input);
  return { input, onSelect, onQueryChange };
};

describe('ComboBox', () => {
  it('selects with the mouse', () => {
    const { onSelect } = setup();
    fireEvent.click(screen.getByText('MSFT'));
    expect(onSelect).toHaveBeenCalledWith('MSFT');
  });

  it('selects with the keyboard', () => {
    const { input, onSelect } = setup();
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('MSFT');
  });

  it('wraps the highlight rather than running off the end', () => {
    const { input, onSelect } = setup();
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('MSFT');
  });

  it('exposes the highlighted option to assistive tech', () => {
    const { input } = setup();
    expect(input).toHaveAttribute('aria-expanded', 'true');
    const before = input.getAttribute('aria-activedescendant');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).not.toBe(before);
  });

  it('closes on Escape without selecting anything', () => {
    const { input, onSelect } = setup();
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('clears its own text after a selection', () => {
    // Otherwise the box still reads "nvd" next to a chosen ticker, which looks
    // like a pending search that never ran.
    const { onQueryChange } = setup();
    fireEvent.click(screen.getByText('NVDA'));
    expect(onQueryChange).toHaveBeenCalledWith('');
  });

  it('says so when a typed query matches nothing', () => {
    setup([], 'zzz');
    expect(screen.getByText('Nothing matches that.')).toBeInTheDocument();
  });

  it('stays quiet when the query is empty and there is nothing to show', () => {
    setup([], '');
    expect(screen.queryByText('Nothing matches that.')).toBeNull();
  });
});
