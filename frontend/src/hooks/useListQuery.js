import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api.js';
import { buildQuery } from '../services/query.js';
import useDebouncedValue from './useDebouncedValue.js';

/*
 * Server-side paginated list with search + filters. Every management screen uses this.
 * Expects the API envelope data: { items, page, per_page, total, pages }.
 *
 *  - search is debounced; changing search or a filter returns to page 1
 *  - only the newest request may update the screen (older, slower responses are ignored)
 *  - if the current page becomes empty (e.g. last row deleted) it steps back to the last page
 */
export default function useListQuery(path, { perPage = 10, initialFilters = {}, debounceMs = 300 } = {}) {
  const [page, setPage] = useState(1);
  const [search, setSearchValue] = useState('');
  const [filters, setFilters] = useState(initialFilters);
  const [state, setState] = useState({ data: null, loading: true, error: '' });
  const [version, setVersion] = useState(0);
  const latest = useRef(0);
  const q = useDebouncedValue(search, debounceMs);

  useEffect(() => { setPage(1); }, [q]);

  useEffect(() => {
    const id = ++latest.current;
    setState((s) => ({ ...s, loading: true, error: '' }));
    api.get(`${path}${buildQuery({ page, per_page: perPage, q, ...filters })}`)
      .then((data) => { if (id === latest.current) setState({ data, loading: false, error: '' }); })
      .catch((err) => { if (id === latest.current) setState({ data: null, loading: false, error: err.message || 'Something went wrong.' }); });
  }, [path, page, perPage, q, filters, version]);

  useEffect(() => {
    const { data, loading } = state;
    if (!loading && data && data.items.length === 0 && data.total > 0 && page > 1) setPage(data.pages);
  }, [state, page]);

  const setSearch = useCallback((value) => setSearchValue(value), []);
  const setFilter = useCallback((key, value) => { setFilters((f) => ({ ...f, [key]: value })); setPage(1); }, []);
  const clearFilters = useCallback(() => { setSearchValue(''); setFilters(initialFilters); setPage(1); }, [initialFilters]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  const hasActiveFilters = search.trim() !== '' || Object.entries(filters).some(([k, v]) => v !== '' && v !== initialFilters[k]);

  return {
    items: state.data?.items ?? [],
    total: state.data?.total ?? 0,
    pages: state.data?.pages ?? 1,
    page,
    perPage,
    loading: state.loading,
    initialLoad: state.loading && state.data === null,
    error: state.error,
    search, setSearch,
    filters, setFilter, clearFilters, hasActiveFilters,
    setPage, reload,
  };
}
