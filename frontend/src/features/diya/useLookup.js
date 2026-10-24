import { useEffect, useState } from 'react';
import { api } from '../../services/api.js';

// Loads a small read-only list once (programs, batch options...) for dropdowns.
// `pick` extracts the array from the response (the paginated lists return { items }).
export default function useLookup(path, pick = (data) => data.items) {
  const [state, setState] = useState({ items: [], loading: true, error: '' });
  useEffect(() => {
    let cancelled = false;
    api.get(path)
      .then((data) => { if (!cancelled) setState({ items: pick(data), loading: false, error: '' }); })
      .catch((err) => { if (!cancelled) setState({ items: [], loading: false, error: err.message }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return state;
}

export const usePrograms = () => useLookup('/programs');
// Up to 100 batches; plenty for one institution. Fetched fresh each time a form opens so seat counts are current.
export const useBatchOptions = () => useLookup('/batches?per_page=100');
