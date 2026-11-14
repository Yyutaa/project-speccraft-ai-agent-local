import { afterEach, expect, test, vi } from 'vitest';
import { api, type Run } from './api';
afterEach(() => vi.unstubAllGlobals());
test('managed approval wraps the existing payload and rereads authoritative workbench', async () => {
  const run = { run_id: 'r', prd_draft: { revision: 2, content_hash: 'hash' }, workbench: { execution_mode: 'managed', run_version: 7 }, managedConfirmation: { actor_claim: 'user', rationale: 'checked', user_confirmed: true } } as unknown as Run;
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 'r' }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ run: { run_id: 'r' }, execution_mode: 'managed', run_version: 8, available_commands: [] }) });
  vi.stubGlobal('fetch', fetch);
  await api.approvePrd(run, 'user', 'checked');
  expect(fetch.mock.calls[0][0]).toBe('/api/managed/runs/r/prd/approve');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ execution_contract_version: 1, expected_run_version: 7, request: { revision: 2, actor: 'user' } });
  expect(fetch.mock.calls[1][0]).toBe('/api/runs/r/workbench');
});

test('managed writes require explicit confirmation without issuing HTTP', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  await expect(api.approveTd({ run_id: 'r', workbench: { execution_mode: 'managed' } } as Run, 'u', 'why')).rejects.toThrow('明确确认');
  expect(fetch).not.toHaveBeenCalled();
});

import { subscribeWorkbench } from './api';
class FakeSource {
  static latest: FakeSource;
  listeners: Record<string, (event: { lastEventId: string }) => void> = {};
  onerror = () => {};
  close = vi.fn();
  constructor(readonly url: string) { FakeSource.latest = this; }
  addEventListener(name: string, listener: (event: { lastEventId: string }) => void) { this.listeners[name] = listener; }
  emit(name: string, id: number) { this.listeners[name]({ lastEventId: String(id) }); }
}
test('SSE coalesces updates, filters duplicates, recalibrates reset and cleans up', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 4, refresh);
  FakeSource.latest.emit('ready', 4);
  FakeSource.latest.emit('update', 5); FakeSource.latest.emit('update', 5);
  vi.advanceTimersByTime(150); expect(refresh).toHaveBeenCalledTimes(1);
  FakeSource.latest.emit('update', 5); vi.advanceTimersByTime(150); expect(refresh).toHaveBeenCalledTimes(1);
  FakeSource.latest.emit('reset', 5); vi.advanceTimersByTime(150); expect(refresh).toHaveBeenCalledTimes(2);
  stop(); vi.advanceTimersByTime(20000); expect(refresh).toHaveBeenCalledTimes(2);
  expect(FakeSource.latest.close).toHaveBeenCalled(); vi.useRealTimers();
});
test('SSE disconnection polls and reconnects with the last cursor', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 4, refresh);
  FakeSource.latest.onerror(); vi.advanceTimersByTime(5150);
  expect(refresh).toHaveBeenCalled(); expect(FakeSource.latest.url).toContain('after=4');
  FakeSource.latest.emit('ready', 4); vi.advanceTimersByTime(150);
  stop(); expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
test('terminal with duplicate cursor triggers final REST and bounded recovery', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); subscribeWorkbench('r', 4, refresh);
  FakeSource.latest.emit('terminal', 4); expect(refresh).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(20000); expect(refresh).toHaveBeenCalledTimes(3);
  expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
test('missing EventSource uses limited frequency polling and cleanup', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', undefined);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 0, refresh);
  vi.advanceTimersByTime(5150); expect(refresh).toHaveBeenCalledTimes(1);
  stop(); expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});

const managedRun = () => ({
  run_id: 'run-1', ledger: { revision: 3 }, technical_decision_requests: [{ request_id: 'technical-1' }],
  prd_draft: { revision: 2, content_hash: 'prd-hash' }, td_draft: { revision: 4, content_hash: 'td-hash' },
  td_review: { review_revision: 6, current_review_id: 'review-1' },
  workbench: { execution_mode: 'managed', run_version: 11 },
  managedConfirmation: { actor_claim: 'user', rationale: 'reviewed', user_confirmed: true },
} as unknown as Run);
test.each([
  ['prd/revisions', (r: Run) => api.revisePrd(r, 'SCOPE', 'body', 'feedback')],
  ['td/revisions', (r: Run) => api.reviseTd(r, 'DATA', 'body', 'feedback', 'user', 'cmd')],
  ['td/reviews', (r: Run) => api.recordTdReview(r, { command_id: 'cmd', actor_claim: 'user', rationale: 'reviewed' } as Parameters<typeof api.recordTdReview>[1])],
  ['td/quality/decisions', (r: Run) => api.decideTdIssue(r, 'issue', 'user', 'reviewed', 'cmd')],
  ['td/quality/risk-acceptances', (r: Run) => api.acceptTdQualityRisk(r, 'issue', 'user', 'reviewed', 'disclosure', 'cmd')],
  ['td/approve', (r: Run) => api.approveTd(r, 'user', 'reviewed')],
  ['td/quality/run', (r: Run) => api.runTdQuality(r, 'user', 2, 'cmd')],
  ['technical-decisions', (r: Run) => api.submitTechnicalDecisions(r, { 'technical-1': 'explicit' }, 'technical-user')],
  ['clarifications', (r: Run) => api.submitClarification(r, [], [], 'user', 'reviewed')],
])('wraps managed %s using current version, preserving business payload', async (route, action) => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) }).mockResolvedValueOnce({ ok: true, json: async () => ({ run: {}, available_commands: [] }) });
  vi.stubGlobal('fetch', fetch);
  await action(managedRun());
  expect(fetch.mock.calls[0][0]).toBe('/api/managed/runs/run-1/' + route);
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body).toMatchObject({ execution_contract_version: 1, expected_run_version: 11, request: { governance_contract_version: 2 } });
  if (route === 'technical-decisions') expect(body.actor_claim).toBe('technical-user');
  expect(fetch.mock.calls[1][0]).toBe('/api/runs/run-1/workbench');
});

test('half-open SSE without onerror closes after 25 seconds and falls back to polling', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 4, refresh);
  const stalled = FakeSource.latest;
  vi.advanceTimersByTime(25000);
  expect(stalled.close).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(5150);
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(FakeSource.latest).not.toBe(stalled);
  stop(); expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
test('heartbeats maintain liveness without triggering REST reads', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 4, refresh);
  const connection = FakeSource.latest;
  for (let n = 0; n < 5; n++) {
    vi.advanceTimersByTime(15000);
    connection.emit('heartbeat', 0);
  }
  expect(refresh).not.toHaveBeenCalled();
  expect(connection.close).not.toHaveBeenCalled();
  stop(); expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
test('expired connection events cannot stop fallback polling or close the replacement connection', () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  const refresh = vi.fn(); const stop = subscribeWorkbench('r', 4, refresh);
  const old = FakeSource.latest;
  old.onerror(); vi.advanceTimersByTime(5150);
  const current = FakeSource.latest;
  expect(refresh).toHaveBeenCalledTimes(1);
  old.emit('ready', 4); old.emit('terminal', 4); old.onerror();
  vi.advanceTimersByTime(5000);
  expect(refresh).toHaveBeenCalledTimes(2);
  expect(current.close).not.toHaveBeenCalled();
  current.emit('ready', 4); vi.advanceTimersByTime(150);
  const count = refresh.mock.calls.length;
  current.emit('heartbeat', 0); vi.advanceTimersByTime(10000);
  expect(refresh).toHaveBeenCalledTimes(count);
  stop(); expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
