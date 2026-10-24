import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom role/name queries are slow on a cold start; give async queries more headroom than the 1s default.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => cleanup());
