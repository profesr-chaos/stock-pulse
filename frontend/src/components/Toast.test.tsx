import { act, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useToast } from '@/hooks/useToast';

import Toast from './Toast';

describe('Toast', () => {
  it('renders nothing without a message', () => {
    const { container } = render(<Toast message={null} onDismiss={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('announces politely rather than stealing focus', () => {
    render(<Toast message="LLM scraping off." onDismiss={vi.fn()} />);
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('LLM scraping off.');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('can be dismissed', () => {
    const onDismiss = vi.fn();
    render(<Toast message="AI summaries on." onDismiss={onDismiss} />);
    screen.getByRole('button', { name: /dismiss/i }).click();
    expect(onDismiss).toHaveBeenCalled();
  });
});

describe('useToast', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('starts empty', () => {
    const { result } = renderHook(() => useToast());
    expect(result.current.message).toBeNull();
  });

  it('shows a message and clears it on its own', () => {
    const { result } = renderHook(() => useToast());

    act(() => result.current.show('LLM scraping on.'));
    expect(result.current.message).toBe('LLM scraping on.');

    act(() => void vi.advanceTimersByTime(4000));
    expect(result.current.message).toBeNull();
  });

  it('a second message replaces the first instead of queueing', () => {
    const { result } = renderHook(() => useToast());

    act(() => result.current.show('LLM scraping off.'));
    act(() => void vi.advanceTimersByTime(1000));
    act(() => result.current.show('LLM scraping on.'));

    expect(result.current.message).toBe('LLM scraping on.');
    // The first message's timer must not cut the second one short.
    act(() => void vi.advanceTimersByTime(2500));
    expect(result.current.message).toBe('LLM scraping on.');
  });

  it('can be dismissed early', () => {
    const { result } = renderHook(() => useToast());
    act(() => result.current.show('AI summaries off.'));
    act(() => result.current.dismiss());
    expect(result.current.message).toBeNull();
  });
});
