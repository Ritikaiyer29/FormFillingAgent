"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { API, api } from "../../lib/api";
import { CALL_LABEL, Shell, STATE_LABEL } from "../../lib/shell";

type Lang = "en" | "hi";

function optionLabel(schema: any, spec: any, code: any, lang: Lang) {
  const opts = spec.enum_ref ? schema.enums[spec.enum_ref] : null;
  const o = opts?.find((x: any) => x.code === code);
  return o ? o[lang] || o.en : String(code);
}

const maskStr = (t: string) => "•".repeat(Math.max(0, t.length - 4)) + t.slice(-4);

// Defined at module level so inputs keep focus while typing (not re-created on every render).
function Val({ ctx, path, spec, value, status, editable = true }: any) {
  const { schema, lang, edit, setEdit, save, snap, submitted } = ctx;
  if (edit?.path === path) {
    return (
      <>
        {spec.type === "enum" || spec.type === "boolean" ? (
          <select value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })}>
            <option value="">-</option>
            {spec.type === "boolean" ? <><option value="yes">Yes</option><option value="no">No</option></> :
              (spec.enum_ref ? schema.enums[spec.enum_ref] : spec.enum.map((c: string) => ({ code: c, en: c }))).map((o: any) => <option key={o.code} value={o.code}>{o[lang] || o.en}</option>)}
          </select>
        ) : <input autoFocus value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && save()} />}
        <button onClick={save}>Save</button><button className="ghost" onClick={() => setEdit(null)}>Cancel</button>
      </>
    );
  }
  if (value === undefined || value === null) return <span className="wait">Waiting for answer</span>;
  const text = spec.type === "enum" ? optionLabel(schema, spec, value, lang) : spec.type === "boolean" ? (value ? "Yes" : "No") : String(value);
  return (
    <>
      <span className={editable && !submitted ? "val" : ""} title={editable && !submitted ? "Click to correct" : ""}
        onClick={() => editable && !submitted && setEdit({ path, value: String(value), rev: snap.revision })}>{spec.log === "never" ? maskStr(text) : text}</span>
      {status === "confirmed" && <span className="tick">✓ Confirmed</span>}
      {status === "captured" && <span className="guess">Heard, to be confirmed</span>}
    </>
  );
}

function Row({ k, children, flash }: any) {
  return <div className={`rw${flash ? " fresh" : ""}`}><div className="k">{k}</div><div className="v">{children}</div></div>;
}

function Session() {
  const params = useSearchParams();
  const id = params.get("id") || "";
  const [schema, setSchema] = useState<any>(null);
  const [snap, setSnap] = useState<any>(null);
  const [lang, setLang] = useState<Lang>("en");
  const [err, setErr] = useState(params.get("started") === "0" ? "The call could not be started. Press Place call to try again." : "");
  const [notice, setNotice] = useState(params.get("started") === "1" ? "Calling now. The phone should ring in a few seconds and the form fills in as the candidate answers." : "");
  const [live, setLive] = useState(false);
  const [edit, setEdit] = useState<{ path: string; value: string; rev: number } | null>(null);
  const [calling, setCalling] = useState(false);
  const [fresh, setFresh] = useState<Record<string, boolean>>({});
  const revRef = useRef(-1);
  const lastEvent = useRef(0);
  const seen = useRef<Record<string, string>>({});

  const take = useCallback((s: any) => {
    if (s.revision < revRef.current) return;  // ignore stale snapshots
    revRef.current = s.revision;
    const now: Record<string, string> = {};
    const changed: Record<string, boolean> = {};
    for (const [k, v] of Object.entries<any>(s.data || {})) {
      now[k] = JSON.stringify(v.value);
      if (Object.keys(seen.current).length && seen.current[k] !== now[k]) changed[k] = true;
    }
    seen.current = now;
    if (Object.keys(changed).length) {
      setFresh((f) => ({ ...f, ...changed }));
      setTimeout(() => setFresh((f) => { const n = { ...f }; Object.keys(changed).forEach((k) => delete n[k]); return n; }), 2800);
    }
    setSnap(s);
  }, []);

  const refresh = useCallback(async () => { take(await api(`/api/sessions/${id}`)); }, [id, take]);

  useEffect(() => {
    api("/api/schema").then(setSchema).catch(() => setErr("Could not load the form. Please refresh."));
    refresh().catch(() => setErr("Could not load this application."));
  }, [id, refresh]);

  // Live updates: reconnect automatically and catch up on anything missed.
  useEffect(() => {
    let es: EventSource | null = null;
    let stopped = false;
    let timer: any;
    const open = async () => {
      try {
        const { token } = await api(`/api/sessions/${id}/stream-token`, { method: "POST" });
        es = new EventSource(`${API}/api/sessions/${id}/events?token=${token}&after=${lastEvent.current}`);
        es.addEventListener("snapshot", (e: any) => { take(JSON.parse(e.data)); setLive(true); });
        es.addEventListener("change", (e: any) => {
          const ev = JSON.parse(e.data);
          if (ev.id <= lastEvent.current) return;
          lastEvent.current = ev.id;
          if (ev.revision > revRef.current) refresh().catch(() => {});
        });
        es.onerror = () => { setLive(false); es?.close(); if (!stopped) timer = setTimeout(open, 2000); };
      } catch { if (!stopped) timer = setTimeout(open, 3000); }
    };
    open();
    return () => { stopped = true; clearTimeout(timer); es?.close(); };
  }, [id, refresh, take]);

  const place = async () => {
    if (!confirm(`Call ${snap.phone} now?`)) return;
    setCalling(true); setErr(""); setNotice("");
    try {
      await api(`/api/sessions/${id}/call`, { method: "POST" });
      setNotice("Calling now. The phone should ring in a few seconds.");
      await refresh();
    } catch (e: any) { setErr(e.message || "The call could not be started."); }
    setTimeout(() => setCalling(false), 15000);
  };

  const save = async () => {
    if (!edit) return;
    try {
      const s = await api(`/api/sessions/${id}/fields`, { method: "POST", body: JSON.stringify({ fields: { [edit.path]: edit.value }, expected_revision: edit.rev }) });
      if (s.validation_errors?.length) { setErr(s.validation_errors[0].message); return; }
      setEdit(null); setErr(""); await refresh();
    } catch (e: any) {
      if (e.status === 409) { setNotice("That detail was just updated by the call. The latest value is shown. Edit again if you still want to change it."); setEdit(null); await refresh(); }
      else setErr(e.message);
    }
  };

  const content = !schema || !snap ? <p className="empty">{err || "Loading..."}</p> : render();
  return <Shell title="Call" active="calls">{content}</Shell>;

  function render() {
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
    const submitted = snap.state === "submitted";
    const called = snap.call_status !== "not_started";

    const steps = [
      { label: "Call placed", done: called },
      { label: "Permission given", done: !!snap.consent_given },
      { label: "Identity checked", done: !!snap.otp_verified },
      { label: `Details collected${snap.otp_verified ? ` (${doneCount} of ${required.length})` : ""}`, done: pct === 100 },
      { label: "Application submitted", done: submitted },
    ];
    const nowIdx = steps.findIndex((s) => !s.done);

    const ctx = { schema, lang, edit, setEdit, save, snap, submitted };

    return (
      <>
        {err && <p className="err">{err}</p>}
        {notice && <p className="notice">{notice}</p>}
        {snap.warnings.map((w: any, i: number) => <p key={i} className="warnbox">{w.message}</p>)}
        <div className="split">
          <aside className="card call-panel">
            <h2>Call</h2>
            <dl className="meta">
              <dt>Mobile</dt><dd>{snap.phone}</dd>
              <dt>Language</dt><dd>{snap.call_language}</dd>
              <dt>Status</dt><dd>{submitted ? STATE_LABEL.submitted : CALL_LABEL[snap.call_status] || snap.call_status}</dd>
            </dl>
            {!submitted && <button className="primary" style={{ width: "100%" }} disabled={calling} onClick={place}>{calling ? "Calling..." : called ? "Call again" : "Place call"}</button>}
            <ul className="steps">
              {steps.map((s, i) => <li key={s.label} className={s.done ? "done" : i === nowIdx && called ? "now" : ""}><span className="dot">{s.done ? "✓" : ""}</span>{s.label}</li>)}
            </ul>
            <div className="bar"><div style={{ width: `${pct}%` }} /></div>
            <p className="empty" style={{ margin: "8px 0 0" }}>{pct}% of required details filled</p>
            {snap.help_requested && <p className="warnbox" style={{ marginTop: 12 }}>The candidate asked for a call back from a person.</p>}
            <p style={{ margin: "14px 0 0" }}>
              <span className={`badge ${live ? "live" : "warn"}`}>{live ? "Updating live" : "Reconnecting..."}</span>
            </p>
          </aside>

          <section className="doc">
            <div className="doc-head">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h2>{variant ? L(schema.variants[variant].label) : "Apprenticeship application form"}</h2>
                  <p>Technical Training Institute, Transport Aircraft Division, HAL Kanpur</p>
                </div>
                <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} style={{ background: "#fff" }} aria-label="Form language">
                  <option value="en">English</option><option value="hi">हिन्दी</option>
                </select>
              </div>
            </div>
            <div className="doc-body">
              {!variant && <p className="empty" style={{ marginTop: 16 }}>The form type (ITI or Vocational) appears once the candidate says which course they passed.</p>}
              {schema.groups.filter(visibleGroup).sort((a: any, b: any) => a.order - b.order).map((g: any) => (
                <div key={g.id}>
                  <div className="sec-title">{L(g.label)}</div>
                  <div className="rows">
                    {schema.fields.filter((f: any) => f.group === g.id && visibleField(f)).sort((a: any, b: any) => a.order - b.order).map((f: any) => {
                      const e = snap.data[f.id];
                      const flash = !!fresh[f.id];
                      if (f.type === "group") {
                        return f.children.map((c: any) => (
                          <Row key={f.id + c.id} k={`${L(f.label)} · ${L(c.label)}`} flash={flash}>
                            <Val ctx={ctx} path={`${f.id}.${c.id}`} spec={c} value={e?.value?.[c.id]} status={e?.value?.[c.id] !== undefined ? e?.status : undefined} />
                          </Row>));
                      }
                      if (f.type === "repeatable") {
                        return [1, 2, 3, 4].map((n) => {
                          const it = e?.value?.[`sem${n}`];
                          if (!it && n > 1) return null;
                          return (
                            <Row key={f.id + n} k={`${L(f.label)} · semester ${n}`} flash={flash}>
                              <span>Marks <Val ctx={ctx} path={`${f.id}.${n}.obtained`} spec={f.item[2]} value={it?.obtained} /> out of <Val ctx={ctx} path={`${f.id}.${n}.total`} spec={f.item[1]} value={it?.total} /></span>
                            </Row>);
                        });
                      }
                      if (f.derived) {
                        const v = snap.derived[f.id];
                        return <Row key={f.id} k={L(f.label)}>{v == null ? <span className="wait">Worked out from the marks</span> : <>{v}%</>}</Row>;
                      }
                      return <Row key={f.id} k={`${L(f.label)}${f.required ? " *" : ""}`} flash={flash}><Val ctx={ctx} path={f.id} spec={f} value={e?.value} status={e?.status} /></Row>;
                    })}
                  </div>
                </div>
              ))}
              <p className="foot-note">Photograph, signature and copies of documents are not taken on the phone. The candidate attaches them to the printed form.</p>
            </div>
          </section>
        </div>
      </>
    );
  }
}

export default function Page() {
  return <Suspense fallback={null}><Session /></Suspense>;
}
