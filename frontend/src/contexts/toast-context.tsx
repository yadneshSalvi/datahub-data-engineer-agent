import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { cn } from "../lib/utils";

type ToastTone = "success" | "error";
interface ToastItem { id: number; title: string; message?: string; tone: ToastTone }
interface ToastContextValue { toast: (item: Omit<ToastItem, "id">) => void }

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((current) => current.filter((item) => item.id !== id)), []);
  const toast = useCallback((item: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((current) => [...current, { ...item, id }]);
    window.setTimeout(() => dismiss(id), 4800);
  }, [dismiss]);
  const value = useMemo(() => ({ toast }), [toast]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[120] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite" aria-label="Notifications">
        <AnimatePresence>
          {items.map((item) => {
            const Icon = item.tone === "success" ? CheckCircle2 : XCircle;
            return <motion.div key={item.id} initial={{ opacity: 0, x: reduced ? 0 : 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reduced ? 0 : 24 }} transition={{ duration: .18 }} className={cn("pointer-events-auto flex gap-3 rounded-xl border bg-surface p-4 shadow-2xl", item.tone === "success" ? "border-ok/35" : "border-critical/35")}><Icon className={cn("mt-0.5 size-4 shrink-0", item.tone === "success" ? "text-ok" : "text-critical")} aria-hidden="true" /><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-fg">{item.title}</p>{item.message && <p className="mt-1 text-xs leading-relaxed text-fg-muted">{item.message}</p>}</div><button type="button" aria-label="Dismiss notification" onClick={() => dismiss(item.id)} className="grid size-7 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-surface-2 hover:text-fg"><X className="size-3.5" aria-hidden="true" /></button></motion.div>;
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used within ToastProvider");
  return value;
}
