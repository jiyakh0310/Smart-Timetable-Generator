import { useEffect, useState } from 'react';

// Live `matchMedia` result. `fallback` is used where matchMedia does not exist (tests, very old browsers).
export default function useMediaQuery(query, fallback = true) {
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function';
  const [matches, setMatches] = useState(() => (supported ? window.matchMedia(query).matches : fallback));
  useEffect(() => {
    if (!supported) return undefined;
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query, supported]);
  return matches;
}
