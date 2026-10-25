import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Button } from './Button.jsx';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Accessible modal: focus moves in, Tab is trapped, Escape / backdrop closes, focus returns on close.
// initialFocus: 'primary' (last button - good for confirmations) or 'first' (first field - good for forms).
export function Dialog({ open, title, onClose, children, initialFocus = 'primary', wide = false }) {
  const panel = useRef(null);
  const titleId = useId();
  // Keep the latest onClose without re-running the focus effect on every parent render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement;
    const items = panel.current?.querySelectorAll(FOCUSABLE);
    const target = initialFocus === 'first' ? items?.[0] : items?.[items.length - 1];
    (target ?? panel.current)?.focus();

    function onKeyDown(e) {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); return; }
      if (e.key !== 'Tab') return;
      const focusables = [...panel.current.querySelectorAll(FOCUSABLE)];
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`dialog${wide ? ' dialog-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={panel} tabIndex={-1}>
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  );
}

// tone "danger" makes the confirm button red - use for destructive actions.
// showCancel={false} turns it into a plain notice with a single OK button.
export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', tone = 'primary', busy = false, showCancel = true, onConfirm, onCancel }) {
  return (
    <Dialog open={open} title={title} onClose={onCancel}>
      <p>{message}</p>
      <div className="dialog-actions">
        {showCancel && <Button variant="secondary" onClick={onCancel}>{cancelLabel}</Button>}
        <Button variant={tone === 'danger' ? 'danger' : tone === 'success' ? 'success' : 'primary'} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}
