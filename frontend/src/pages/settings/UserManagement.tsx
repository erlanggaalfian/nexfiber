import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router";
import * as z from "zod";
import { Empty, ErrorState, PageTitle, Skeleton, fmtDateTime } from "../../components/data";
import { Button } from "../../components/ui/button";
import { api, qs, type Role } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export type UserRow = {
  id: number; username: string; full_name: string; role: Role; admin_id: number | null;
  admin_username: string | null; olt_count: number; is_active: boolean;
  must_change_password: boolean; last_login_at: string | null; created_at: string;
};

const ROLE_LABEL: Record<Role, string> = { superadmin: "Superadmin", admin: "Admin", user: "User" };
const input = "h-8 w-full rounded-sm border border-line-strong bg-surface px-2 text-sm";
const cell = "px-3 py-2 text-left align-middle";

const schema = z.object({
  username: z.string().min(3).max(64).regex(/^[a-zA-Z0-9_.-]+$/, "Hanya huruf, angka, . _ -"),
  full_name: z.string().min(1).max(255),
  password: z.string().max(128).refine((v) => v === "" || v.length >= 12, "Minimal 12 karakter"),
  role: z.enum(["admin", "user"]),
  admin_id: z.string(),
});
type Form = z.infer<typeof schema>;

const useUsers = (role: string, enabled: boolean) =>
  useQuery({ queryKey: ["users", role], queryFn: () => api<UserRow[]>(`/api/users${qs({ role })}`), enabled });

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-down">{error}</span>}
    </label>
  );
}

/** PRD 3.4.9 add/edit. Superadmin picks role + parent Admin; an Admin only creates Users. */
function UserDrawer({ edit, onClose }: { edit: UserRow | null; onClose: () => void }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const isSuper = me.role === "superadmin";
  const admins = useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => api<UserRow[]>("/api/users?role=admin"),
    enabled: isSuper,
  });
  const { register, handleSubmit, watch, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: edit?.username ?? "",
      full_name: edit?.full_name ?? "",
      password: "",
      role: (edit?.role === "admin" ? "admin" : "user") as "admin" | "user",
      admin_id: edit?.admin_id ? String(edit.admin_id) : "",
    },
  });
  const save = useMutation({
    mutationFn: (f: Form) => {
      const body: Record<string, unknown> = { full_name: f.full_name, role: f.role };
      if (f.password) body.password = f.password;
      if (isSuper && f.role === "user") body.admin_id = Number(f.admin_id) || null;
      if (!isSuper) delete body.role;
      if (edit) return api<UserRow>(`/api/users/${edit.id}`, { method: "PATCH", json: body });
      return api<UserRow>("/api/users", {
        method: "POST",
        json: { ...body, username: f.username, password: f.password, role: f.role },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });
  const role = watch("role");

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l bg-surface shadow-modal data-[state=closed]:animate-[drawer-out_200ms_ease-in] data-[state=open]:animate-[drawer-in_250ms_ease-out]">
          <Dialog.Title className="border-b px-4 py-3 text-lg font-semibold">
            {edit ? `Edit ${edit.username}` : "Tambah user"}
          </Dialog.Title>
          <form onSubmit={handleSubmit((f) => save.mutate(f))} className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {!edit && (
                <Field label="Username" error={formState.errors.username?.message}>
                  <input className={input} autoFocus autoComplete="off" {...register("username")} />
                </Field>
              )}
              <Field label="Nama" error={formState.errors.full_name?.message}>
                <input className={input} autoComplete="off" {...register("full_name")} />
              </Field>
              <Field
                label={edit ? "Password baru (kosong = tidak diubah)" : "Password"}
                error={formState.errors.password?.message}
              >
                <input className={input} type="password" autoComplete="new-password" {...register("password")} />
              </Field>
              {isSuper && (
                <Field label="Peran">
                  <select className={input} {...register("role")}>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                </Field>
              )}
              {isSuper && role === "user" && (
                <Field label="Admin induk">
                  <select className={input} required {...register("admin_id")}>
                    <option value="">Pilih Admin</option>
                    {(admins.data ?? []).map((a) => (
                      <option key={a.id} value={a.id}>{a.username}</option>
                    ))}
                  </select>
                </Field>
              )}
              {save.isError && <p className="text-down" role="alert">{save.error.message}</p>}
            </div>
            <div className="flex justify-end gap-2 border-t px-4 py-3">
              <Dialog.Close asChild><Button>Batal</Button></Dialog.Close>
              <Button type="submit" variant="fiber" disabled={save.isPending}>
                {save.isPending ? "Menyimpan ..." : "Simpan"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Confirm({ title, body, action, onConfirm, onClose, error, busy }: {
  title: string; body: string; action: string; onConfirm: () => void; onClose: () => void;
  error?: string; busy?: boolean;
}) {
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-md border bg-surface p-4 shadow-modal">
          <Dialog.Title className="mb-2 text-lg font-semibold">{title}</Dialog.Title>
          <p className="mb-4 text-muted">{body}</p>
          {error && <p className="mb-3 text-down" role="alert">{error}</p>}
          <div className="flex justify-end gap-2">
            <Dialog.Close asChild><Button>Tutup</Button></Dialog.Close>
            <Button variant="primary" onClick={onConfirm} disabled={busy}>{action}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function UserManagement() {
  const { me, isManager } = useAuth();
  const qc = useQueryClient();
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState<{ edit: UserRow | null } | null>(null);
  const [off, setOff] = useState<UserRow | null>(null);
  const [reset, setReset] = useState<UserRow | null>(null);
  const [temp, setTemp] = useState("");
  const users = useUsers(role, isManager);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });
  const deactivate = useMutation({
    mutationFn: (u: UserRow) => api<UserRow>(`/api/users/${u.id}`, { method: "PATCH", json: { is_active: false } }),
    onSuccess: () => { invalidate(); setOff(null); },
  });
  const resetPw = useMutation({
    mutationFn: (u: UserRow) => api<{ password: string }>(`/api/users/${u.id}/reset-password`, { method: "POST" }),
    onSuccess: (r) => { invalidate(); setReset(null); setTemp(r.password); },
  });

  const term = q.trim().toLowerCase();
  const rows = (users.data ?? []).filter(
    (u) => !term || u.username.toLowerCase().includes(term) || u.full_name.toLowerCase().includes(term),
  );

  // Menu already hides this page for role "user"; a typed URL stops here (backend also 403s).
  if (!isManager) return <Navigate to="/" replace />;

  return (
    <>
      <PageTitle title="User Management">
        <Button variant="fiber" onClick={() => setDrawer({ edit: null })}>Tambah user</Button>
      </PageTitle>

      <div className="mb-3 flex flex-wrap gap-2">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Cari username atau nama"
          className="h-8 w-60 rounded-sm border border-line-strong bg-surface px-2 text-sm placeholder:text-faint"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Filter peran"
          className="h-8 rounded-sm border border-line-strong bg-surface px-2 text-sm"
        >
          <option value="">Semua peran</option>
          {me.role === "superadmin" && <option value="superadmin">Superadmin</option>}
          {me.role === "superadmin" && <option value="admin">Admin</option>}
          <option value="user">User</option>
        </select>
      </div>

      <section className="entrance rounded-md border bg-surface">
        {users.isPending ? (
          <Skeleton text="Memuat user ..." rows={4} />
        ) : users.isError ? (
          <ErrorState message={users.error.message} onRetry={() => users.refetch()} />
        ) : rows.length === 0 ? (
          <Empty>Belum ada user.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b">
                  <th className={cell}>Username</th>
                  <th className={cell}>Nama</th>
                  <th className={cell}>Peran</th>
                  <th className={cell}>Admin induk</th>
                  <th className={cell}>OLT</th>
                  <th className={cell}>Aktif</th>
                  <th className={cell}>Login terakhir</th>
                  <th className={cell}>Dibuat</th>
                  <th className={cell}>Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id} className="border-b last:border-0">
                    <td className={`${cell} font-mono`}>{u.username}</td>
                    <td className={cell}>{u.full_name}</td>
                    <td className={cell}>{ROLE_LABEL[u.role]}</td>
                    <td className={cell}>{u.admin_username ?? "—"}</td>
                    <td className={`${cell} font-mono`}>{u.role === "user" ? "—" : u.olt_count}</td>
                    <td className={cell}>
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`size-1.5 shrink-0 ${u.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                        {u.is_active ? "Aktif" : "Nonaktif"}
                      </span>
                    </td>
                    <td className={cell}>{fmtDateTime(u.last_login_at)}</td>
                    <td className={cell}>{fmtDateTime(u.created_at)}</td>
                    <td className={cell}>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => setDrawer({ edit: u })}>Edit</Button>
                        <Button size="sm" onClick={() => setReset(u)}>Reset password</Button>
                        {u.is_active && u.id !== me.id && (
                          <Button size="sm" variant="danger" onClick={() => setOff(u)}>Nonaktifkan</Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {drawer && <UserDrawer edit={drawer.edit} onClose={() => setDrawer(null)} />}
      {off && (
        <Confirm
          title={`Nonaktifkan ${off.username}?`}
          body="User tidak dihapus, hanya tidak bisa login lagi."
          action="Nonaktifkan"
          busy={deactivate.isPending}
          error={deactivate.error?.message}
          onConfirm={() => deactivate.mutate(off)}
          onClose={() => { deactivate.reset(); setOff(null); }}
        />
      )}
      {reset && (
        <Confirm
          title={`Reset password ${reset.username}?`}
          body="Password lama langsung tidak berlaku; password sementara ditampilkan sekali."
          action="Reset"
          busy={resetPw.isPending}
          error={resetPw.error?.message}
          onConfirm={() => resetPw.mutate(reset)}
          onClose={() => { resetPw.reset(); setReset(null); }}
        />
      )}
      {temp && (
        <Dialog.Root open onOpenChange={() => setTemp("")}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
            <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-md border bg-surface p-4 shadow-modal">
              <Dialog.Title className="mb-2 text-lg font-semibold">Password sementara</Dialog.Title>
              <p className="mb-3 text-muted">Catat sekarang; tidak bisa dilihat lagi.</p>
              <p className="mb-4 rounded-sm bg-sunken px-2 py-1.5 font-mono select-all">{temp}</p>
              <div className="flex justify-end">
                <Dialog.Close asChild><Button variant="fiber">Selesai</Button></Dialog.Close>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </>
  );
}
