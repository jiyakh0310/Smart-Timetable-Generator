// Thin fetch wrapper for the Flask API. Every response uses the same envelope:
//   { success: true, data }  or  { success: false, error: { code, message, details } }
const BASE = import.meta.env.VITE_API_BASE || '/api/v1';
const TOKEN_KEY = 'timetable.token';

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || {};
  }
}

// localStorage can throw (private mode / blocked storage), so every access is guarded.
export const tokenStore = {
  get() {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token) {
    try { localStorage.setItem(TOKEN_KEY, token); } catch { /* ignore */ }
  },
  clear() {
    try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

let onUnauthorized = null;
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Is the backend running?');
  }

  let payload = null;
  try { payload = await response.json(); } catch { /* non-JSON response */ }

  if (!response.ok || !payload || payload.success === false) {
    const err = payload?.error || {};
    if (response.status === 401 && auth && onUnauthorized) onUnauthorized();
    throw new ApiError(
      response.status,
      err.code || 'request_failed',
      err.message || `Request failed (${response.status})`,
      err.details,
    );
  }
  return payload.data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body, options) => request(path, { method: 'POST', body, ...options }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
};
