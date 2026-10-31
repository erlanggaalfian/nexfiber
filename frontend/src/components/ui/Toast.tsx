import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckCircle, Info, Warning, X } from "@phosphor-icons/react";

/* Sistem toast (DESIGN §13): hanya untuk hasil job yang selesai saat user sudah
   pindah halaman. Maksimal 3 toast tampil; sukses/info hilang sendiri 5 detik,
   error menetap sampai ditutup tombol ×.
   Posisi: fixed kanan bawah di desktop; di <768px di ATAS bottom nav
   (64px + safe-area + 12px) supaya tidak tertutup navigasi bawah.
   Animasi memakai keyframe `fade-in` yang sudah ada di styles/index.css
   (fade + naik 4px, 200ms = motion-fade), mati saat prefers-reduced-motion. */

export type ToastKind = "success" | "error" | "info";

type ToastItem = { id: number; kind: ToastKind; message: string };

export type ToastApi = {
  success: (message: string) => number;
  error: (message: string) => number;
  info: (message: string) => number;
  dismiss: (id: number) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const MAX_TOASTS = 3;
const AUTO_DISMISS_MS = 5000;

const KIND_META: Record<ToastKind, { icon: typeof Info; iconClass: string; role: "status" | "alert" }> = {
  success: { icon: CheckCircle, iconClass: "text-up", role: "status" },
  error: { icon: Warning, iconClass: "text-down", role: "alert" },
  info: { icon: Info, iconClass: "text-fiber", role: "status" },
};

function ToastCard({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const meta = KIND_META[item.kind];
  const Icon = meta.icon;
  return (
    <div
      role={meta.role}
      className="pointer-events-auto flex animate-[fade-in_200ms_ease-out] items-start gap-2 rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-ink shadow-overlay motion-reduce:animate-none"
    >
      <Icon size={16} className={`mt-0.5 shrink-0 ${meta.iconClass}`} aria-hidden />
      <p className="min-w-0 flex-1 break-words">{item.message}</p>
      {item.kind === "error" && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Tutup notifikasi"
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-sunken hover:text-ink"
        >
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++;
      // FIFO: toast ke-4 menggeser yang paling lama, total tidak pernah > 3.
      setItems((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, kind, message }]);
      if (kind !== "error") {
        timers.current.set(id, setTimeout(() => dismiss(id), AUTO_DISMISS_MS));
      }
      return id;
    },
    [dismiss],
  );

  // Bersihkan semua timer saat provider dilepas.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  const api: ToastApi = {
    success: (message) => push("success", message),
    error: (message) => push("error", message),
    info: (message) => push("info", message),
    dismiss,
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* z-50: di atas overlay modal (z-40) dan bottom nav (z-40) agar notifikasi
          hasil job tetap terlihat walau dialog sedang terbuka. */}
      <div className="pointer-events-none fixed right-6 bottom-6 z-50 flex w-80 max-w-[calc(100vw-3rem)] flex-col gap-2 max-md:right-4 max-md:bottom-[calc(64px+env(safe-area-inset-bottom)+12px)] max-md:left-4 max-md:w-auto">
        {items.map((item) => (
          <ToastCard key={item.id} item={item} onClose={() => dismiss(item.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast harus dipakai di dalam <ToastProvider>");
  return ctx;
}
