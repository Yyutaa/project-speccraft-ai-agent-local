import { Alert, Button, Space } from 'antd';
import { useEffect, useState } from 'react';
import { api, type PublishedArtifact, type RuntimeStatus } from './api';

export function ArtifactDownloads({ runId, artifacts, disabled = false }: { runId: string; artifacts: PublishedArtifact[]; disabled?: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function download(artifact: PublishedArtifact) {
    setBusy(true); setError(null);
    try { await api.downloadArtifact(runId, artifact); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '下载失败，请重新读取 Run'); }
    finally { setBusy(false); }
  }
  if (!artifacts.length) return null;
  return <section aria-label="正式交付物下载"><h3>正式交付物</h3><Space wrap>{artifacts.map((artifact) => <Button key={artifact.kind} disabled={disabled || busy} onClick={() => void download(artifact)}>下载 {artifact.filename}</Button>)}</Space>{error && <Alert type="error" showIcon title={error} />}</section>;
}

const workerLabels = { running: '运行中', disabled: '未启动', stale: '状态过期', exited: '已退出', unknown: '状态未知' };
export function WorkerStatus() {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try { const value = await api.runtime(); if (!disposed) { setRuntime(value); setError(null); } }
      catch (reason) { if (!disposed) { setRuntime(null); setError(reason instanceof Error && reason.message.includes('404') ? '非监督启动，无法读取 Worker 状态；请确认已独立启动 Worker 和配置 Provider。' : '无法读取 Worker 状态，请检查本地服务。'); } }
      finally { if (!disposed) timer = setTimeout(() => void refresh(), 5000); }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); };
  }, []);
  return <Alert showIcon type={runtime?.worker.status === 'running' ? 'success' : 'warning'} title={`Worker ${runtime ? workerLabels[runtime.worker.status] : '状态未知'}`} description={error ?? runtime?.worker.reason ?? (runtime ? (!runtime.worker.configured ? '缺少 Provider 配置，后台模型任务不可执行。' : '运行状态仅供参考，操作权限以服务器返回为准。') : '正在读取本地 Worker 状态')} />;
}
