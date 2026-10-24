import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import Icon from './Icon.jsx';

const ToastContext = createContext(null);
const TONE_ICON = { success: 'check', danger: 'alert', info: 'info' };
let nextId = 1;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  // toast({ tone: 'success' | 'danger' | 'info', title, message })
  const toast = useCallback(({ tone = 'info', title, message }) => {
    const id = nextId++;
    setToasts((list) => [...list, { id, tone, title, message }]);
    setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);

  const value = useMemo(() => ({ toast }), [toast]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <Icon name={TONE_ICON[t.tone]} size={18} />
            <div>
              <strong>{t.title}</strong>
              {t.message && <span>{t.message}</span>}
            </div>
            <button type="button" className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx.toast;
}
