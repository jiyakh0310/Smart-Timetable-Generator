// Jiya - R18: "Export PDF" / "Export Excel". The file is fetched with the signed-in token (a plain link could not send it) and saved by the browser.
import { useState } from 'react';
import { Button, Icon, Notice } from '../../components/ui';
import { api } from '../../services/api.js';
import { saveBlob } from '../../services/download.js';

const FORMATS = [
  { format: 'pdf', label: 'Export PDF' },
  { format: 'xlsx', label: 'Export Excel' },
];

export default function ExportButtons({ path, termId, disabled = false }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  async function run(format) {
    setBusy(format);
    setError('');
    setDone('');
    try {
      const query = `?format=${format}${termId ? `&term_id=${termId}` : ''}`;
      const { blob, filename } = await api.download(`${path}${query}`);
      saveBlob(blob, filename);
      setDone(`${filename} was downloaded.`);
    } catch (err) {
      setError(err.message || 'The export could not be created.');
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="export-buttons">
      <div className="export-row" role="group" aria-label="Export this timetable">
        {FORMATS.map(({ format, label }) => (
          <Button key={format} variant="secondary" size="sm" onClick={() => run(format)} loading={busy === format} disabled={disabled || Boolean(busy)}>
            <Icon name="download" size={15} /> {label}
          </Button>
        ))}
      </div>
      <div aria-live="polite">
        {error && <Notice tone="danger">{error}</Notice>}
        {done && <span className="text-muted">{done}</span>}
      </div>
    </div>
  );
}
