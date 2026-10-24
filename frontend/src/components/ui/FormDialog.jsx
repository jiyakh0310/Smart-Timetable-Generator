import { Button } from './Button.jsx';
import { Dialog } from './Dialog.jsx';
import { Notice } from './Feedback.jsx';

// Modal form: focus starts on the first field, Escape cancels, Enter submits.
// `error` is a form-level message (server errors); field errors are shown by the fields themselves.
export default function FormDialog({ open, title, description, error, busy = false, submitLabel = 'Save', onClose, onSubmit, children, wide = false }) {
  return (
    <Dialog open={open} title={title} onClose={onClose} initialFocus="first" wide={wide}>
      {description && <p className="dialog-desc">{description}</p>}
      <form className="form" noValidate onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        {error && <Notice tone="danger">{error}</Notice>}
        {children}
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" loading={busy}>{submitLabel}</Button>
        </div>
      </form>
    </Dialog>
  );
}
