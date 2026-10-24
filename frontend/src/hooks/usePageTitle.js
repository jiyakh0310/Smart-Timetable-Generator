import { useEffect } from 'react';

const SUFFIX = 'Smart Timetable';

export default function usePageTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${SUFFIX}` : SUFFIX;
  }, [title]);
}
