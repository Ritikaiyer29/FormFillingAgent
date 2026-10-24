"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { API, api } from "../../lib/api";

type Lang = "en" | "hi";

function optionLabel(schema: any, spec: any, code: any, lang: Lang) {
  const opts = spec.enum_ref ? schema.enums[spec.enum_ref] : null;
  const o = opts?.find((x: any) => x.code === code);
  return o ? o[lang] || o.en : String(code);
}

function Session() {
  const id = useSearchParams().get("id") || "";
  const [schema, setSchema] = useState<any>(null);
  const [snap, setSnap] = useState<any>(null);
  const [lang, setLang] = useState<Lang>("en");
  const [err, setErr] = useState("");
  const [conn, setConn] = useState<"live" | "reconnecting">("reconnecting");
  const [edit, setEdit] = useState<{ path: string; value: string; rev: number } | null>(null);
  const [conflict, setConflict] = useState("");
  const revRef = useRef(-1);
  const lastEvent = useRef(0);

  const refresh = useCallback(async () => {
    const s = await api(`/api/sessions/${id}`);
    if (s.revision >= revRef.current) { revRef.current = s.revision; setSnap(s); }  // ignore stale snapshots
  }, [id]);

  useEffect(() => {
    api("/api/schema").then(setSchema).catch((e) => setErr(e.message));
    refresh().catch((e) => setErr(e.message));
  }, [id, refresh]);

  // SSE with durable replay: reconnect with a fresh short-lived token and the last seen event id.
  useEffect(() => {
    let es: EventSource | null = null;
    let stopped = false;
    let timer: any;
    const open = async () => {
      try {
        const { token } = await api(`/api/sessions/${id}/stream-token`, { method: "POST" });
        es = new EventSource(`${API}/api/sessions/${id}/events?token=${token}&after=${lastEvent.current}`);
        es.addEventListener("snapshot", (e: any) => {
          const s = JSON.parse(e.data);
          if (s.revision >= revRef.current) { revRef.current = s.revision; setSnap(s); }
          setConn("live");
        });
        es.addEventListener("change", (e: any) => {
          const ev = JSON.parse(e.data);
          if (ev.id <= lastEvent.current) return;  // duplicate
          lastEvent.current = ev.id;
          if (ev.revision > revRef.current) refresh().catch(() => {});
        });
        es.onerror = () => {
          setConn("reconnecting");
          es?.close();
          if (!stopped) timer = setTimeout(open, 2000);
        };
      } catch { if (!stopped) timer = setTimeout(open, 3000); }
    };
    open();
    return () => { stopped = true; clearTimeout(timer); es?.close(); };
  }, [id, refresh]);

  const save = async () => {
    if (!edit) return;
    try {
      const s = await api(`/api/sessions/${id}/fields`, { method: "POST", body: JSON.stringify({ fields: { [edit.path]: edit.value }, expected_revision: edit.rev }) });
      if (s.validation_errors?.length) { setErr(s.validation_errors[0].message); return; }
      setEdit(null); setErr(""); await refresh();
    } catch (e: any) {
      if (e.status === 409) { setConflict(`${edit.path} changed while you were editing. Latest value loaded; re-apply your edit if still needed.`); setEdit(null); await refresh(); }
      else setErr(e.message);
    }
  };

  if (!schema || !snap) return <main><p>{err || "Loading..."}</p></main>;

  const L = (o: any) => (o?.[lang] || o?.en || "");
  const variant = snap.variant;
  const visibleGroup = (g: any) => !g.when || g.when.variant === variant;
  const visibleField = (f: any) => {
    const g = schema.groups.find((x: any) => x.id === f.group);
    if (g?.when && g.when.variant !== variant) return false;
    if (f.when?.variant && f.when.variant !== variant) return false;
    if (f.when?.field && !f.when.in.includes(snap.data[f.when.field]?.value)) return false;
    return true;
  };
  const required = schema.fields.filter((f: any) => f.required && !f.derived && visibleField(f) && f.id !== "variant");
  const doneCount = required.filter((f: any) => !snap.missing.some((m: string) => m === f.id || m.startsWith(f.id + "."))).length;
  const pct = required.length ? Math.round((100 * doneCount) / required.length) : 0;
  const locked = snap.state === "submitted";

  const Value = ({ path, spec, value, status, editable = true }: any) => {
    const editing = edit?.path === path;
    if (editing) {
      return (
        <span className="row" style={{ gap: 6 }}>
          {spec.type === "enum" || spec.type === "boolean" ? (
            <select value={edit!.value} onChange={(e) => setEdit({ ...edit!, value: e.target.value })}>
              <option value="">-</option>
              {spec.type === "boolean" ? <><option value="yes">Yes</option><option value="no">No</option></> :
                (spec.enum_ref ? schema.enums[spec.enum_ref] : spec.enum.map((c: string) => ({ code: c, en: c }))).map((o: any) => <option key={o.code} value={o.code}>{o[lang] || o.en}</option>)}
            </select>
          ) : <input autoFocus value={edit!.value} onChange={(e) => setEdit({ ...edit!, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && save()} />}
          <button onClick={save}>Save</button><button className="ghost" onClick={() => setEdit(null)}>Cancel</button>
        </span>
      );
    }
    const text = value === undefined || value === null ? null :
      spec.type === "enum" ? optionLabel(schema, spec, value, lang) : spec.type === "boolean" ? (value ? "Yes" : "No") : String(value);
    return (
      <span>
        {text === null ? <span className="empty">waiting</span> :
          <span className={editable && !locked ? "val" : ""} onClick={() => editable && !locked && setEdit({ path, value: String(value), rev: snap.revision })}>{spec.log === "never" ? maskStr(text) : text}</span>}
        {status && <> <span className={`badge ${status}`}>{status}</span></>}
      </span>
    );
  };
  const maskStr = (t: string) => "•".repeat(Math.max(0, t.length - 4)) + t.slice(-4);

  return (
    <main>
      <p><a href="/">&larr; All applications</a></p>
      <h1>{variant ? L(schema.variants[variant].label) : "Application"}</h1>
      <p className="sub">
        {snap.phone} · call language {snap.call_language}{snap.language_locked ? " (locked)" : ""} · revision {snap.revision} ·{" "}
        <span className={`badge ${snap.state}`}>{snap.state}</span> · call {snap.call_status} · delivery {snap.delivery_status} ·{" "}
        <span className={conn === "live" ? "" : "warn"}>{conn === "live" ? "live" : "reconnecting..."}</span>
      </p>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span>Progress: {doneCount} of {required.length} required fields</span>
          <label>Form language
            <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              <option value="en">English</option><option value="hi">हिन्दी (labels)</option>
            </select>
          </label>
        </div>
        <div className="bar" style={{ marginTop: 8 }}><div style={{ width: `${pct}%` }} /></div>
        <p style={{ margin: "8px 0 0" }}>
          Consent: {snap.consent_given ? "given" : "not yet"} · Code check: {snap.otp_verified ? "verified (dummy)" : "not yet"}
          {snap.help_requested && <span className="warn"> · human callback requested</span>}
        </p>
      </div>
      {conflict && <div className="banner">{conflict} <button className="ghost" onClick={() => setConflict("")}>Dismiss</button></div>}
      {err && <p className="err">{err}</p>}
      {snap.warnings.map((w: any, i: number) => <p key={i} className="warn">⚠ {w.message}</p>)}
      <p className="sub">Values appear as the agent saves them. They are field updates, not a call transcript. Click a value to correct it.</p>

      {schema.groups.filter(visibleGroup).sort((a: any, b: any) => a.order - b.order).map((g: any) => (
        <div className="card" key={g.id}>
          <h2>{L(g.label)}</h2>
          <table><tbody>
            {schema.fields.filter((f: any) => f.group === g.id && visibleField(f)).sort((a: any, b: any) => a.order - b.order).map((f: any) => {
              const e = snap.data[f.id];
              if (f.type === "group") {
                return f.children.map((c: any) => (
                  <tr key={f.id + c.id}><td>{L(f.label)} · {L(c.label)}</td>
                    <td><Value path={`${f.id}.${c.id}`} spec={c} value={e?.value?.[c.id]} status={e?.value?.[c.id] !== undefined ? e?.status : undefined} /></td></tr>));
              }
              if (f.type === "repeatable") {
                return [1, 2, 3, 4].map((n) => {
                  const it = e?.value?.[`sem${n}`];
                  if (!it && n > 1) return null;
                  return (
                    <tr key={f.id + n}><td>{L(f.label)} · semester {n}</td>
                      <td>total <Value path={`${f.id}.${n}.total`} spec={f.item[1]} value={it?.total} /> · obtained <Value path={`${f.id}.${n}.obtained`} spec={f.item[2]} value={it?.obtained} /> {it && <span className={`badge ${e.status}`}>{e.status}</span>}</td></tr>);
                });
              }
              if (f.derived) {
                const v = snap.derived[f.id];
                return <tr key={f.id}><td>{L(f.label)}</td><td>{v == null ? <span className="empty">computed when marks are in</span> : <>{v}% <span className="badge">computed</span></>}</td></tr>;
              }
              return <tr key={f.id}><td>{L(f.label)}{f.required ? " *" : ""}</td>
                <td><Value path={f.id} spec={f} value={e?.value} status={e?.status} /></td></tr>;
            })}
          </tbody></table>
        </div>
      ))}
      <p className="sub">Photograph, signature and enclosure checklist are not collected by voice; the candidate attaches them to the printed form.</p>
    </main>
  );
}

export default function Page() {
  return <Suspense fallback={<main>Loading...</main>}><Session /></Suspense>;
}
