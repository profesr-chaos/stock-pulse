import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Masthead from './Masthead';

/**
 * The masthead is the ambient indicator for LLM grading, so the two states
 * have to be distinguishable from the DOM: flickering while grading runs,
 * flat black when it does not.
 */
const letters = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('span[aria-hidden="true"]'));

describe('Masthead', () => {
  it('still reads as "Stock Pulse" to assistive tech', () => {
    render(<Masthead flicker />);
    // Split into per-letter spans, so without the sr-only copy this is empty.
    expect(screen.getByText('Stock Pulse')).toBeInTheDocument();
  });

  it('renders one span per character', () => {
    const { container } = render(<Masthead flicker={false} />);
    expect(letters(container)).toHaveLength('Stock Pulse'.length);
  });

  it('flickers every letter when grading is on', () => {
    const { container } = render(<Masthead flicker />);
    const spans = letters(container);

    expect(spans).not.toHaveLength(0);
    expect(spans.every((s) => s.classList.contains('animate-rgb-flicker'))).toBe(true);
  });

  it('gives each letter its own timing so they are out of phase', () => {
    const { container } = render(<Masthead flicker />);
    const delays = letters(container).map(
      (s) => (s as HTMLElement).style.getPropertyValue('--flicker-delay'),
    );

    expect(delays.every(Boolean)).toBe(true);
    // Randomised per letter — a single shared delay would flash in unison.
    expect(new Set(delays).size).toBeGreaterThan(1);
  });

  it('is black and static when grading is off', () => {
    const { container } = render(<Masthead flicker={false} />);
    const spans = letters(container);

    expect(spans.every((s) => s.classList.contains('animate-rgb-flicker'))).toBe(false);
    expect(
      spans.every((s) => (s as HTMLElement).style.color === 'rgb(0, 0, 0)'),
    ).toBe(true);
    // No animation variables at all, not just an unused animation.
    expect(
      spans.every((s) => !(s as HTMLElement).style.getPropertyValue('--flicker-delay')),
    ).toBe(true);
  });

  it('falls back to black underneath the animation', () => {
    // prefers-reduced-motion kills the keyframes; the base colour is what is
    // left, and it has to be legible rather than whatever the cycle started on.
    const { container } = render(<Masthead flicker />);
    expect(
      letters(container).every((s) => (s as HTMLElement).style.color === 'rgb(0, 0, 0)'),
    ).toBe(true);
  });
});
