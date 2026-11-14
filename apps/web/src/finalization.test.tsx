import { afterEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { api, type PublishedArtifact } from './api';
import { ArtifactDownloads, WorkerStatus } from './Finalization';
const artifact: PublishedArtifact = { kind: 'prd', filename: 'PRD.md', revision: 2, content_hash: 'abc', media_type: 'text/markdown' };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
test('downloads exact server binding and fixed name with delayed URL cleanup', async () => {
 vi.useFakeTimers();
 const fetch = vi.fn().mockResolvedValue(new Response('approved', { headers: { 'X-Content-SHA256': 'abc' } })); vi.stubGlobal('fetch', fetch);
 const create = vi.fn().mockReturnValue('blob:approved'); const revoke = vi.fn(); vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
 const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
 await api.downloadArtifact('r/x', artifact);
 expect(fetch.mock.calls[0][0]).toBe('/api/runs/r%2Fx/artifacts/prd?revision=2&content_hash=abc');
 expect(create).toHaveBeenCalledTimes(1); expect((click.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe('PRD.md'); expect(revoke).not.toHaveBeenCalled(); await vi.advanceTimersByTimeAsync(30000); expect(revoke).toHaveBeenCalledWith('blob:approved'); click.mockRestore();
});
test.each([new Response(JSON.stringify({ detail: { code: 'artifact_binding_conflict' } }), { status: 409 }), new Response('wrong', { headers: { 'X-Content-SHA256': 'wrong' } })])('failed download never creates a file', async (response) => {
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response)); const create = vi.fn(); vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create }));
 await expect(api.downloadArtifact('r', artifact)).rejects.toThrow(); expect(create).not.toHaveBeenCalled();
});
test('only server manifest offers downloads and failure is visible', async () => {
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 409 })));
 const { rerender } = render(<ArtifactDownloads runId="r" artifacts={[]} />); expect(screen.queryByRole('button')).toBeNull();
 rerender(<ArtifactDownloads runId="r" artifacts={[artifact]} />); fireEvent.click(screen.getByRole('button', { name: '下载 PRD.md' })); await waitFor(() => expect(screen.getByText(/请求失败：409/)).toBeTruthy());
});
test('worker offline reason and 404 fallback do not affect run and stop polling on unmount', async () => {
 const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ supervised: true, worker: { status: 'disabled', configured: false, reason: '缺少 Provider 配置', pid: null } }))); vi.stubGlobal('fetch', fetch);
 const { unmount } = render(<WorkerStatus />); await waitFor(() => expect(screen.getByText(/缺少 Provider 配置/)).toBeTruthy()); unmount();
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })));
 render(<WorkerStatus />); await waitFor(() => expect(screen.getByText(/非监督启动/)).toBeTruthy());
});

test('worker polling waits five seconds and cleanup cancels the next read', async () => {
 vi.useFakeTimers();
 const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ supervised: true, worker: { status: 'running', configured: true, reason: null, pid: 123 } }))); vi.stubGlobal('fetch', fetch);
 const { unmount } = render(<WorkerStatus />);
 await vi.advanceTimersByTimeAsync(0); expect(fetch).toHaveBeenCalledTimes(1);
 await vi.advanceTimersByTimeAsync(4999); expect(fetch).toHaveBeenCalledTimes(1);
 await vi.advanceTimersByTimeAsync(1); expect(fetch).toHaveBeenCalledTimes(2);
 unmount(); await vi.advanceTimersByTimeAsync(15000); expect(fetch).toHaveBeenCalledTimes(2);
});
