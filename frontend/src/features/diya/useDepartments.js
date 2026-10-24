import { useEffect, useState } from 'react';
import { api } from '../../services/api.js';

// Departments are a small read-only lookup used by dropdowns (loaded once per screen).
export default function useDepartments() {
  const [state, setState] = useState({ items: [], loading: true, error: '' });
  useEffect(() => {
    let cancelled = false;
    api.get('/departments')
      .then((data) => { if (!cancelled) setState({ items: data.items, loading: false, error: '' }); })
      .catch((err) => { if (!cancelled) setState({ items: [], loading: false, error: err.message }); });
    return () => { cancelled = true; };
  }, []);
  return state;
}
