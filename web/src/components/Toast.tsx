"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

interface ToastItem {
  id: number;
  message: string;
  tone: "ok" | "fail";
}

interface ToastContextValue {
  push: (message: string, tone?: "ok" | "fail") => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, tone: "ok" | "fail" = "fail") => {
    const id = nextId++;
    setItems((cur) => [...cur, { id, message, tone }]);
    setTimeout(() => {
      setItems((cur) => cur.filter((t) => t.id !== id));
    }, 3200);
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 items-end">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.18 }}
              role="status"
              data-testid="toast"
              className={`flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-sm shadow-lg shadow-black/40 backdrop-blur ${
                t.tone === "ok"
                  ? "border-lime/30 bg-lime-soft text-lime"
                  : "border-coral/30 bg-coral-soft text-coral"
              }`}
            >
              {t.tone === "ok" ? (
                <CheckCircle2 size={15} className="shrink-0" />
              ) : (
                <AlertTriangle size={15} className="shrink-0" />
              )}
              <span className="text-text">{t.message}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
