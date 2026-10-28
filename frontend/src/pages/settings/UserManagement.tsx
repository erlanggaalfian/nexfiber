import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router";
import * as z from "zod";
import { Empty, ErrorState, PageTitle, Skeleton, fmtDateTime } from "../../components/data";
import { Field, filterInput, input } from "../../components/crud";
import { ConfirmShell, DrawerShell, ModalShell, PasswordInput } from "../../components/onu/modals/ModalShell";
import { Button } from "../../components/ui/button";
import { api, qs, type Olt, type Role } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export type UserRow = {
  id: number; username: string; full_name: string; role: Role; admin_id: number | null;
  admin_username: string | null; olt_count: number; is_active: boolean;
  must_change_password: boolean; last_login_at: string | null; created_at: string;
};

const ROLE_LABEL: Record<Role, string> = { superadmin: "Superadmin", admin: "Admin", user: "User" };

const schema = z.object({
  username: z.string().min(3).max(64).regex(/^[a-zA-Z0-9_.-]+$/, "Hanya huruf, angka, . _ -"),
  full_name: z.string().min(1).max(255),
  password: z.string().max(128).refine((v) => v === "" || v.length >= 12, "Minimal 12 karakter"),
  role: z.enum(["superadmin", "admin", "user"]),
  admin_id: z.string(),
});
type Form = z.infer<typeof schema>;

const useUsers = (role: string, enabled: boolean) =>
  useQuery({ queryKey: ["users", role], queryFn: () => api<UserRow[]>(`/api/users${qs({ role })}`), enabled });

/** PRD 3.4.9 add/edit. Role options follow PRD 3.7: Superadmin may create any role,
 *  an Admin may create Admin/User (its Users land under itself). Changing the role of an
 *  existing user stays Superadmin-only. */
function UserDrawer({ edit, onClose }: { edit: UserRow | null; onClose: () => void }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const isSuper = me.role === "superadmin";
  const mayPickRole = isSuper || !edit;
  const admins = useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => api<UserRow[]>("/api/users?role=admin"),
    enabled: isSuper,
  });
  const { register, handleSubmit, watch, setValue, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: edit?.username ?? "",
      full_name: edit?.full_name ?? "",
      password: "",
      role: edit?.role ?? "user",
      admin_id: edit?.admin_id ? String(edit.admin_id) : "",
    },
  });
  // Checklist OLT = tabel olt_access, satu-satunya tempat akses OLT diatur (Superadmin
  // saja, PRD 3.7). Role "user" tidak punya baris sendiri: aksesnya ikut Admin induknya.
  const olts = useQuery({
    queryKey: ["olts"],
    queryFn: () => api<Olt[]>("/api/olts"),
    enabled: isSuper,
  });
  const access = useQuery({
    queryKey: ["users", "olt-access", edit?.id],
    queryFn: () => api<{ olt_ids: number[] }>(`/api/users/${edit?.id}/olt-access`),
    enabled: isSuper && !!edit,
  });
  const [picked, setPicked] = useState<number[] | null>(null);
  const oltIds = picked ?? access.data?.olt_ids ?? [];
  const toggleOlt = (id: number) =>
    setPicked(oltIds.includes(id) ? oltIds.filter((x) => x !== id) : [...oltIds, id]);

  const save = useMutation({
    mutationFn: async (f: Form) => {
      const body: Record<string, unknown> = { full_name: f.full_name, role: f.role };
      if (f.password) body.password = f.password;
      if (isSuper && f.role === "user") body.admin_id = Number(f.admin_id) || null;
      if (!isSuper) delete body.role;
      // PENYIMPANGAN dari instruksi literal "hapus role di POST bila bukan
      // Superadmin", dengan alasan: UserCreate.role wajib diisi dan Admin
      // memang boleh membuat Admin/User (PRD 3.7) — menghapus role sepenuhnya
      // membuat POST Admin selalu 422. Bug sebenarnya adalah `role: f.role`
      // lama yang menimpa penghapusan di body, sehingga nilai superadmin
      // yang diselundupkan ikut terkirim. Perilaku sekarang: PATCH tetap
      // tanpa role untuk non-Superadmin (mengubah peran memang Superadmin
      // saja); POST mengembalikan role HANYA bila admin/user (yang memang
      // boleh dibuat Admin), dan TIDAK mengembalikan superadmin — jadi
      // percobaan eskalasi lewat POST tidak lagi terkirim, sementara
      // pembuatan Admin/User oleh Admin tetap jalan. Backend _may_set_role
      // tetap menjadi penegak terakhir.
      const postBody: Record<string, unknown> = { ...body, username: f.username, password: f.password };
      if (!isSuper && (f.role === "admin" || f.role === "user")) postBody.role = f.role;
      const saved = edit
        ? await api<UserRow>(`/api/users/${edit.id}`, { method: "PATCH", json: body })
        : await api<UserRow>("/api/users", { method: "POST", json: postBody });
      if (isSuper && f.role !== "user" && picked) {
        await api<{ olt_ids: number[] }>(`/api/users/${saved.id}/olt-access`, {
          method: "PUT",
          json: { olt_ids: picked },
        });
      }
      return saved;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });
  const role = watch("role");

  return (
    <DrawerShell
      title={edit ? `Edit ${edit.username}` : "Tambah user"}
      dirty={formState.isDirty || picked !== null}
      onClose={onClose}
      onSubmit={() => void handleSubmit((f) => save.mutate(f))()}
      busy={save.isPending}
      error={save.isError ? save.error.message : undefined}
    >
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
                <PasswordInput label="Password" value={watch("password") ?? ""}
                               onChange={(v) => setValue("password", v, { shouldValidate: true })} />
              </Field>
              {mayPickRole && (
                <Field label="Peran">
                  <select className={input} {...register("role")}>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                    {isSuper && <option value="superadmin">Superadmin</option>}
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
              {isSuper && role !== "user" && (
                <Field label="OLT yang dikelola">
                  {olts.isPending || access.isPending ? (
                    <p className="text-muted">Memuat OLT ...</p>
                  ) : (olts.data ?? []).length === 0 ? (
                    <p className="text-muted">Belum ada OLT.</p>
                  ) : (
                    <div className="max-h-56 overflow-y-auto rounded-sm border p-1">
                      {(olts.data ?? []).map((o) => (
                        <label
                          key={o.id}
                          className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken max-md:py-3"
                        >
                          <input
                            type="checkbox"
                            checked={oltIds.includes(o.id)}
                            onChange={() => toggleOlt(o.id)}
                          />
                          <span className="truncate">{o.name}</span>
                          <span className="ml-auto font-mono text-xs text-muted">{o.host}</span>
                        </label>
                      ))}
                    </div>
                  )}
                  <span className="mt-1 block text-xs text-muted">
                    OLT milik user ini tetap bisa dikelola walau tidak dicentang.
                  </span>
                </Field>
              )}
    </DrawerShell>
  );
}

function Confirm({ title, body, action, onConfirm, onClose, error, busy, danger }: {
  title: string; body: string; action: string; onConfirm: () => void; onClose: () => void;
  error?: string; busy?: boolean; danger?: boolean;
}) {
  return (
    <ConfirmShell title={title} body={body} action={action} danger={danger ?? false}
                  onConfirm={onConfirm} onClose={onClose} error={error} busy={busy} />
  );
}

export function UserManagement() {
  const { me, isManager } = useAuth();
  const qc = useQueryClient();
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState<{ edit: UserRow | null } | null>(null);
  const [off, setOff] = useState<UserRow | null>(null);
  const [del, setDel] = useState<UserRow | null>(null);
  const [reset, setReset] = useState<UserRow | null>(null);
  const [temp, setTemp] = useState("");
  const users = useUsers(role, isManager);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });
  const setActive = useMutation({
    mutationFn: ({ u, is_active }: { u: UserRow; is_active: boolean }) =>
      api<UserRow>(`/api/users/${u.id}`, { method: "PATCH", json: { is_active } }),
    onSuccess: () => { invalidate(); setOff(null); },
  });
  const remove = useMutation({
    mutationFn: (u: UserRow) => api<void>(`/api/users/${u.id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setDel(null); },
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
          className={`${filterInput} w-60`}
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Filter peran"
          className={filterInput}
        >
          <option value="">Semua peran</option>
          {me.role === "superadmin" && <option value="superadmin">Superadmin</option>}
          {me.role === "superadmin" && <option value="admin">Admin</option>}
          <option value="user">User</option>
        </select>
      </div>

      <section className="entrance rounded-lg border border-line/60 bg-surface shadow-xs">
        {users.isPending ? (
          <Skeleton text="Memuat user ..." rows={4} />
        ) : users.isError ? (
          <ErrorState message={users.error.message} onRetry={() => users.refetch()} />
        ) : rows.length === 0 ? (
          <Empty>Belum ada user.</Empty>
        ) : (
          <>
          <div className="grid gap-2 p-2 md:hidden">
            {rows.map((u) => (
              <article key={u.id} className="min-h-[72px] rounded-lg border border-line/60 bg-surface px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-medium">{u.full_name}</span>
                  <span className="inline-flex shrink-0 items-center gap-1.5 text-xs">
                    <span className={`size-1.5 shrink-0 ${u.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                    {u.is_active ? "Aktif" : "Nonaktif"}
                  </span>
                </div>
                <p className="truncate font-mono text-xs text-muted">
                  {u.username} · {ROLE_LABEL[u.role]}
                  {u.admin_username ? ` · ${u.admin_username}` : ""}
                </p>
                <div className="mt-1 flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => setDrawer({ edit: u })}>Edit</Button>
                  <Button size="sm" onClick={() => setReset(u)}>Reset password</Button>
                  {u.id !== me.id && (u.is_active ? (
                    <Button size="sm" variant="danger" onClick={() => setOff(u)}>Nonaktifkan</Button>
                  ) : (
                    <Button size="sm" disabled={setActive.isPending} onClick={() => setActive.mutate({ u, is_active: true })}>Aktifkan</Button>
                  ))}
                  {u.id !== me.id && (
                    <Button size="sm" variant="danger" onClick={() => setDel(u)}>Hapus</Button>
                  )}
                </div>
              </article>
            ))}
          </div>
          <div className="hidden overflow-x-auto md:block">
            <table className="tbl tbl--sticky">
              <thead>
                <tr>
                  <th scope="col">Username</th>
                  <th scope="col">Nama</th>
                  <th scope="col">Peran</th>
                  <th scope="col">Admin induk</th>
                  <th scope="col">OLT</th>
                  <th scope="col">Aktif</th>
                  <th scope="col">Login terakhir</th>
                  <th scope="col">Dibuat</th>
                  <th scope="col">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id}>
                    <td className="font-mono">{u.username}</td>
                    <td>{u.full_name}</td>
                    <td>{ROLE_LABEL[u.role]}</td>
                    <td>{u.admin_username ?? "—"}</td>
                    <td className="font-mono">{u.role === "user" ? "—" : u.olt_count}</td>
                    <td>
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`size-1.5 shrink-0 ${u.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                        {u.is_active ? "Aktif" : "Nonaktif"}
                      </span>
                    </td>
                    <td>{fmtDateTime(u.last_login_at)}</td>
                    <td>{fmtDateTime(u.created_at)}</td>
                    <td>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => setDrawer({ edit: u })}>Edit</Button>
                        <Button size="sm" onClick={() => setReset(u)}>Reset password</Button>
                        {u.id !== me.id && (
                          u.is_active ? (
                            <Button size="sm" variant="danger" onClick={() => setOff(u)}>Nonaktifkan</Button>
                          ) : (
                            <Button
                              size="sm"
                              disabled={setActive.isPending}
                              onClick={() => setActive.mutate({ u, is_active: true })}
                            >
                              Aktifkan
                            </Button>
                          )
                        )}
                        {u.id !== me.id && (
                          <Button size="sm" variant="danger" onClick={() => setDel(u)}>Hapus</Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </section>

      {drawer && <UserDrawer edit={drawer.edit} onClose={() => setDrawer(null)} />}
      {off && (
        <Confirm
          title={`Nonaktifkan ${off.username}?`}
          body="User tidak dihapus, hanya tidak bisa login lagi."
          action="Nonaktifkan"
          busy={setActive.isPending}
          error={setActive.error?.message}
          onConfirm={() => setActive.mutate({ u: off, is_active: false })}
          onClose={() => { setActive.reset(); setOff(null); }}
        />
      )}
      {del && (
        <Confirm danger
          title={`Hapus ${del.username}?`}
          body="User hilang dari daftar tapi tetap tersimpan (soft-delete) supaya Logs dan kepemilikan OLT lama tetap utuh. Tidak bisa login lagi."
          action="Hapus"
          busy={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate(del)}
          onClose={() => { remove.reset(); setDel(null); }}
        />
      )}
      {reset && (
        <Confirm
          title={`Reset password ${reset.username}?`}
          body="Password lama langsung tidak berlaku; password sementara ditampilkan sekali dan wajib diganti saat login berikutnya."
          action="Reset"
          busy={resetPw.isPending}
          error={resetPw.error?.message}
          onConfirm={() => resetPw.mutate(reset)}
          onClose={() => { resetPw.reset(); setReset(null); }}
        />
      )}
      {temp && (
        <ModalShell title="Password sementara" onClose={() => setTemp("")} closeLabel="Selesai">
          <p className="mb-3 text-muted">Catat sekarang; tidak bisa dilihat lagi.</p>
          <p className="rounded-sm bg-surface px-2 py-1.5 font-mono select-all">{temp}</p>
        </ModalShell>
      )}
    </>
  );
}
