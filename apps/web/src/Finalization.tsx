import { Alert, Button, Space } from 'antd';
import { useState } from 'react';
import { api, type PublishedArtifact } from './api';

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
