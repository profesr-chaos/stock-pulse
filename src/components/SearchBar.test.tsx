import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DEFAULT_FILTER, type FeedFilter } from '@/hooks/useStockNews';

import SearchBar from './SearchBar';

vi.mock('@/hooks/useSectors', () => ({
  useSectors: () => ({
    data: [
      { sector: 'Industrials', level: 'group', group: null, stockCount: 3 },
      {
        sector: 'Aerospace & Defense',
        level: 'industry',
        group: 'Industrials',
        stockCount: 1,
      },
    ],
  }),
}));

vi.mock('@/hooks/useWatchlist', () => ({
  useWatchlist: () => ({
    watchlist: [
      { symbol: 'NVDA', name: 'Nvidia' },
      { symbol: 'MSFT', name: 'Microsoft' },
      { symbol: '6RJ0', name: 'Rocket Lab Corp' },
    ],
  }),
}));

const setup = (filter: Partial<FeedFilter> = {}) => {
  const onChange = vi.fn();
  const onClear = vi.fn();
  render(
    <SearchBar filter={{ ...DEFAULT_FILTER, ...filter }} onChange={onChange} onClear={onClear} />,
  );
  return { onChange, onClear };
};

const newsBox = () => screen.getByRole('searchbox', { name: 'Search news' });
const tickerBox = () => screen.getByRole('combobox', { name: 'Filter news by stock ticker' });

describe('SearchBar', () => {
  it('searches news on Enter', () => {
    const { onChange } = setup();
    fireEvent.change(newsBox(), { target: { value: 'launch failure' } });
    fireEvent.keyDown(newsBox(), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith({ query: 'launch failure' });
  });

  it('leaves the ticker filter alone when searching', () => {
    // They are separate controls now, so "NVDA + launch" is a legitimate
    // combination rather than two settings fighting each other.
    const { onChange } = setup({ symbol: 'NVDA' });
    fireEvent.change(newsBox(), { target: { value: 'launch' } });
    fireEvent.keyDown(newsBox(), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith({ query: 'launch' });
  });

  it('commits an empty query when the box is cleared', () => {
    // The native clear button on a search input fires no Enter, so without
    // this the results would stay up with an empty box.
    const { onChange } = setup({ query: 'launch' });
    fireEvent.input(newsBox(), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith({ query: '' });
  });

  it('filters the feed by a followed ticker', () => {
    const { onChange } = setup();
    fireEvent.focus(tickerBox());
    fireEvent.click(screen.getByText('6RJ0'));
    expect(onChange).toHaveBeenCalledWith({ symbol: '6RJ0' });
  });

  it('searches within the followed tickers', () => {
    // The point of the searchable dropdown: a long watchlist must not become
    // an unscannable list.
    setup();
    fireEvent.focus(tickerBox());
    fireEvent.change(tickerBox(), { target: { value: 'rocket' } });
    expect(screen.getByText('6RJ0')).toBeInTheDocument();
    expect(screen.queryByText('NVDA')).toBeNull();
  });

  it('matches a ticker by symbol as well as name', () => {
    setup();
    fireEvent.focus(tickerBox());
    fireEvent.change(tickerBox(), { target: { value: 'msf' } });
    expect(screen.getByText('MSFT')).toBeInTheDocument();
  });

  it('shows the chosen ticker as a chip that clears itself', () => {
    const { onChange } = setup({ symbol: 'NVDA' });
    // By name, not by text: "NVDA" also appears in the clear-all summary.
    fireEvent.click(screen.getByRole('button', { name: /clear the ticker filter/ }));
    expect(onChange).toHaveBeenCalledWith({ symbol: null });
  });

  it('reports a sector choice as a filter change', () => {
    const { onChange } = setup();
    fireEvent.change(screen.getByLabelText('Sector'), { target: { value: 'Industrials' } });
    expect(onChange).toHaveBeenCalledWith({ sector: 'Industrials' });
  });

  it('clears the sector back to null, not the empty string', () => {
    // '' would be sent to the API as a sector named "", which matches nothing.
    const { onChange } = setup({ sector: 'Industrials' });
    fireEvent.change(screen.getByLabelText('Sector'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith({ sector: null });
  });

  it('offers both sector levels so broad and narrow both filter', () => {
    setup();
    expect(screen.getByRole('option', { name: /^Industrials/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Aerospace & Defense/ })).toBeInTheDocument();
  });

  it('reports a sort choice as a filter change', () => {
    const { onChange } = setup();
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'sentiment' } });
    expect(onChange).toHaveBeenCalledWith({ sort: 'sentiment' });
  });

  it('offers a way back to the unfiltered feed', () => {
    const { onClear } = setup({ sector: 'Industrials' });
    fireEvent.click(screen.getByText('clear all'));
    expect(onClear).toHaveBeenCalled();
  });

  it('shows no clear button when nothing is filtered', () => {
    setup();
    expect(screen.queryByText('clear all')).toBeNull();
  });
});
