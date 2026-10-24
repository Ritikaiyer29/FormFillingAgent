"use client";
import { useEffect, useState } from "react";
import { api, getKey, setKey } from "../lib/api";

const LANGUAGES = ["Hindi", "English", "Assamese", "Bengali", "Gujarati", "Kannada", "Konkani", "Malayalam", "Marathi", "Odia", "Punjabi", "Tamil", "Telugu"];

export default function Home() {
  const [key, setKeyState] = useState("");
  const [authed, setAuthed] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("Hindi");
  const [variant, setVariant] = useState("");

  const load = async () => {
    try { setRows(await api("/api/sessions")); setAuthed(true); setErr(""); }
    catch (e: any) { setAuthed(false); setErr(e.status === 401 ? "" : e.message); }
  };
  useEffect(() => { if (getKey()) load(); }, []);

  const login = () => { setKey(key); load(); };
  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const s = await api("/api/sessions", { method: "POST", body: JSON.stringify({ phone, language, variant: variant || null }) });
      window.location.href = `/session?id=${s.id}`;
    } catch (e: any) { setErr(e.body?.detail?.[0]?.msg || e.message); }
  };

  if (!authed) {
    return (
      <main>
        <h1>Form Filling Agent</h1>
        <p className="sub">Operator sign-in</p>
        <div className="card row">
          <label>Admin key<input type="password" value={key} onChange={(e) => setKeyState(e.target.value)} /></label>
          <button onClick={login}>Sign in</button>
        </div>
        {getKey() && <p className="err">Could not sign in. Check the admin key and that the API is reachable.</p>}
        {err && <p className="err">{err}</p>}
      </main>
    );
  }

  return (
    <main>
      <h1>Form Filling Agent</h1>
      <p className="sub">HAL Kanpur apprentice application. Applications are created here; the call is dispatched separately.</p>
      <form className="card row" onSubmit={create}>
        <label>Candidate phone<input required placeholder="98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        <label>Call language
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>{LANGUAGES.map((l) => <option key={l}>{l}</option>)}</select>
        </label>
        <label>Application type
          <select value={variant} onChange={(e) => setVariant(e.target.value)}>
            <option value="">Ask on call</option><option value="ITI">ITI (Form-A)</option><option value="VOCATIONAL">Vocational (Form-B)</option>
          </select>
        </label>
        <button type="submit">New application</button>
      </form>
      {err && <p className="err">{err}</p>}
      <div className="card">
        <h2>Applications</h2>
        {rows.length === 0 ? <p className="empty">None yet.</p> : (
          <table>
            <thead><tr><th>Phone</th><th>Type</th><th>State</th><th>Call</th><th>Created</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td>{r.phone}</td><td>{r.variant || "-"}</td>
                <td><span className={`badge ${r.state}`}>{r.state}</span></td><td>{r.call_status}</td>
                <td>{new Date(r.created_at).toLocaleString()}</td><td><a href={`/session?id=${r.id}`}>Open</a></td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
    </main>
  );
}
