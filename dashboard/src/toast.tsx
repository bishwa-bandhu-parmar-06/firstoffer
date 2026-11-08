// Small notifications at the bottom of the screen, optionally with one action button.
import { useEffect, useState } from "react";

interface Toast {
  id: number;
  message: string;
  action?: { label: string; run: () => void };
  ms: number;
}

let nextId = 1;
const listeners = new Set<(t: Toast) => void>();

export function toast(message: string, action?: Toast["action"], ms = action ? 8000 : 2500) {
  const t = { id: nextId++, message, action, ms };
  listeners.forEach((l) => l(t));
}

export function Toaster() {
  const [items, setItems] = useState<Toast[]>([]);

  useEffect(() => {
    const add = (t: Toast) => {
      setItems((current) => [...current.slice(-2), t]);
      window.setTimeout(() => setItems((current) => current.filter((x) => x.id !== t.id)), t.ms);
    };
    listeners.add(add);
    return () => { listeners.delete(add); };
  }, []);

  const dismiss = (id: number) => setItems((current) => current.filter((x) => x.id !== id));

  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className="toast">
          <span>{t.message}</span>
          {t.action && (
            <button className="toast-action" onClick={() => { t.action!.run(); dismiss(t.id); }}>{t.action.label}</button>
          )}
          <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">✕</button>
        </div>
      ))}
    </div>
  );
}
