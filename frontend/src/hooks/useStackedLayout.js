import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const PER_COLUMN = 112;  // px a column needs to stay readable before the table should become cards
const BASE = 60;

/*
 * Decides whether a data table should render as stacked, labelled cards instead of a wide grid.
 * It stacks when the container is narrower than the columns need (columns x 112px), and also whenever the real table
 * turns out to overflow its container, remembering the width at which that happened so it does not flip back and forth.
 * Where ResizeObserver does not exist (tests) it never stacks, so the plain table markup is what tests see.
 */
export default function useStackedLayout(wrapRef, columnCount, watch) {
  const [width, setWidth] = useState(null);
  const [overflowAt, setOverflowAt] = useState(0);
  const first = useRef(true);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver((entries) => setWidth(Math.round(entries[0].contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, [wrapRef]);

  // New data can change how wide the natural table is: measure again from scratch.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    setOverflowAt(0);
  }, [watch]);

  const needed = columnCount * PER_COLUMN + BASE;
  const stacked = width !== null && (width < needed || width <= overflowAt);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (stacked || width === null || !el) return;
    const table = el.querySelector('table');
    if (table && table.scrollWidth > el.clientWidth + 1) setOverflowAt(width);
  });

  return stacked;
}
