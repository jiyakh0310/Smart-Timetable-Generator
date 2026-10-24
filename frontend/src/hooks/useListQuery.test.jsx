import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import useListQuery from './useListQuery.js';

const get = vi.fn();
vi.mock('../services/api.js', () => ({ api: { get: (...a) => get(...a) } }));

const pageOf = (items, extra = {}) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1, ...extra });
const lastUrl = () => get.mock.calls[get.mock.calls.length - 1][0];

beforeEach(() => { get.mockReset(); });

describe('useListQuery', () => {
  it('loads the first page and exposes the rows', async () => {
    get.mockResolvedValue(pageOf([{ id: 1 }, { id: 2 }], { total: 2 }));
    const { result } = renderHook(() => useListQuery('/things', { perPage: 10 }));
    expect(result.current.initialLoad).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(2);
    expect(result.current.total).toBe(2);
    expect(get).toHaveBeenCalledWith('/things?page=1&per_page=10');
  });

  it('debounces search, then queries once and returns to page 1', async () => {
    get.mockResolvedValue(pageOf([{ id: 1 }], { total: 40, pages: 4 }));
    const { result } = renderHook(() => useListQuery('/things', { debounceMs: 30 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setPage(3));
    await waitFor(() => expect(lastUrl()).toContain('page=3'));
    get.mockClear();

    act(() => { result.current.setSearch('3'); });
    expect(get).not.toHaveBeenCalled(); // nothing sent while still typing
    await waitFor(() => expect(lastUrl()).toContain('q=3'));
    expect(lastUrl()).toContain('page=1');
    expect(result.current.hasActiveFilters).toBe(true);
  });

  it('filters reset to page 1 and empty filter values are left out of the URL', async () => {
    get.mockResolvedValue(pageOf([{ id: 1 }], { total: 40, pages: 4 }));
    const { result } = renderHook(() => useListQuery('/things', { initialFilters: { day: '', slot_type: '' } }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setPage(2));
    await waitFor(() => expect(lastUrl()).toContain('page=2'));
    act(() => result.current.setFilter('day', '2'));
    await waitFor(() => expect(lastUrl()).toContain('day=2'));
    expect(lastUrl()).toContain('page=1');
    expect(lastUrl()).not.toContain('slot_type');
  });

  it('clearFilters resets search, filters and page', async () => {
    get.mockResolvedValue(pageOf([]));
    const { result } = renderHook(() => useListQuery('/things', { initialFilters: { day: '' }, debounceMs: 10 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { result.current.setFilter('day', '1'); result.current.setSearch('x'); });
    await waitFor(() => expect(result.current.hasActiveFilters).toBe(true));
    act(() => result.current.clearFilters());
    await waitFor(() => expect(result.current.hasActiveFilters).toBe(false));
    await waitFor(() => expect(lastUrl()).toBe('/things?page=1&per_page=10'));
  });

  it('ignores an older, slower response that arrives after a newer one', async () => {
    let resolveSlow;
    get.mockImplementationOnce(() => new Promise((r) => { resolveSlow = r; })); // first request: slow
    get.mockResolvedValue(pageOf([{ id: 'new' }])); // later requests: fast
    const { result } = renderHook(() => useListQuery('/things'));
    act(() => result.current.setFilter('day', '1')); // triggers the second, faster request
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'new' }]));
    await act(async () => { resolveSlow(pageOf([{ id: 'old' }])); });
    expect(result.current.items).toEqual([{ id: 'new' }]);
  });

  it('reports errors and recovers on reload', async () => {
    get.mockRejectedValueOnce(new Error('Cannot reach the server.'));
    get.mockResolvedValue(pageOf([{ id: 1 }]));
    const { result } = renderHook(() => useListQuery('/things'));
    await waitFor(() => expect(result.current.error).toBe('Cannot reach the server.'));
    expect(result.current.items).toEqual([]);
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.error).toBe('');
  });

  it('steps back to the last page when the current page becomes empty (e.g. last row deleted)', async () => {
    get.mockImplementation((url) => Promise.resolve(url.includes('page=3') ? pageOf([], { page: 3, total: 20, pages: 2 }) : pageOf([{ id: 1 }], { total: 20, pages: 2 })));
    const { result } = renderHook(() => useListQuery('/things'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setPage(3));
    await waitFor(() => expect(result.current.page).toBe(2));
  });
});
