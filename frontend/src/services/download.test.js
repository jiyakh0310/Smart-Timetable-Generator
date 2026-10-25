import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, setUnauthorizedHandler, tokenStore } from './api.js';
import { saveBlob } from './download.js';

const file = (init = {}) => new Response('%PDF-fake', { status: 200, headers: { 'Content-Disposition': 'attachment; filename="timetable-A-v1.pdf"', 'Content-Type': 'application/pdf' }, ...init });
const json = (status, error) => new Response(JSON.stringify({ success: false, error }), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  tokenStore.set('abc');
});
afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.clear();
  setUnauthorizedHandler(null);
});

describe('api.download', () => {
  it('sends the bearer token and returns the file with its server-chosen name', async () => {
    fetch.mockResolvedValue(file());
    const result = await api.download('/student/timetable/export?format=pdf');
    expect(fetch).toHaveBeenCalledWith('/api/v1/student/timetable/export?format=pdf', { headers: { Accept: '*/*', Authorization: 'Bearer abc' } });
    expect(result.filename).toBe('timetable-A-v1.pdf');
    expect(await result.blob.text()).toBe('%PDF-fake');
  });

  it('turns the error envelope into an ApiError with the server message and code', async () => {
    fetch.mockResolvedValue(json(404, { code: 'no_published_timetable', message: 'Nothing published yet.' }));
    await expect(api.download('/x')).rejects.toMatchObject({ status: 404, code: 'no_published_timetable', message: 'Nothing published yet.' });
    await expect(api.download('/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('has a readable message when the error is not JSON', async () => {
    fetch.mockResolvedValue(new Response('boom', { status: 500 }));
    await expect(api.download('/x')).rejects.toMatchObject({ message: 'The export failed (500).' });
  });

  it('signs the user out on 401', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetch.mockResolvedValue(json(401, { code: 'unauthorized', message: 'Session expired.' }));
    await expect(api.download('/x')).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalled();
  });

  it('reports a network failure clearly', async () => {
    fetch.mockRejectedValue(new TypeError('failed'));
    await expect(api.download('/x')).rejects.toMatchObject({ code: 'network_error' });
  });

  it('works without a token header when signed out (the server then answers 401)', async () => {
    tokenStore.clear();
    fetch.mockResolvedValue(json(401, { code: 'unauthorized', message: 'x' }));
    await expect(api.download('/x')).rejects.toBeInstanceOf(ApiError);
    expect(fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });
});

describe('saveBlob', () => {
  it('creates a temporary link with the file name, clicks it and tidies up', () => {
    const create = vi.fn(() => 'blob:fake');
    const revoke = vi.fn();
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.useFakeTimers();
    saveBlob(new Blob(['x']), 'timetable.xlsx');
    expect(create).toHaveBeenCalled();
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[download]')).toBeNull();      // the link is removed again
    vi.advanceTimersByTime(1500);
    expect(revoke).toHaveBeenCalledWith('blob:fake');
    vi.useRealTimers();
    click.mockRestore();
  });
});
