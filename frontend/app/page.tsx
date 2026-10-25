"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Shell } from "../lib/shell";
import { ApplicationsTable } from "../lib/table";

const LANGUAGES = ["Hindi", "English", "Assamese", "Bengali", "Gujarati", "Kannada", "Konkani", "Malayalam", "Marathi", "Odia", "Punjabi", "Tamil", "Telugu"];

export default function Home() {
  const [rows, setRows] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("Hindi");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api("/api/sessions").then(setRows).catch(() => {}); }, []);

  const digits = phone.replace(/\D/g, "");
  const valid = digits.length === 10;

  const place = async () => {
    setBusy(true); setErr("");
    let id = "";
    try {
      const s = await api("/api/sessions", { method: "POST", body: JSON.stringify({ phone: digits, language, candidate_name: name.trim() || null }) });
      id = s.id;
      await api(`/api/sessions/${id}/call`, { method: "POST" });
      window.location.href = `/session?id=${id}&started=1`;
    } catch (e: any) {
      if (id) { window.location.href = `/session?id=${id}&started=0`; return; }
      setErr(e.body?.detail?.[0]?.msg || "Could not start. Please check the number and try again.");
      setBusy(false);
    }
  };

  const done = rows.filter((r) => r.state === "submitted").length;
  const active = rows.filter((r) => r.state === "collecting" || r.state === "ready_for_submission").length;

  const top = (
    <>
      <label className="field">Candidate name (optional)
        <input placeholder="Enter name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>Mobile number
        <div className="phone"><span>+91</span><input inputMode="numeric" placeholder="10-digit number" value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
      </label>
      <label className="field" style={{ width: 140 }}>Language
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>{LANGUAGES.map((l) => <option key={l}>{l}</option>)}</select>
      </label>
      <button className="primary" disabled={!valid || busy} onClick={place}>{busy ? "Calling..." : "Place call"}</button>
    </>
  );

  return (
    <Shell title="Calls" active="calls" top={top}>
      {err && <p className="err">{err}</p>}
      <div className="stats">
        <div className="stat"><b>{rows.length}</b><span>Applications</span></div>
        <div className="stat"><b>{active}</b><span>In progress</span></div>
        <div className="stat"><b>{done}</b><span>Submitted</span></div>
      </div>
      <div className="card">
        <h2>Recent applications</h2>
        <ApplicationsTable rows={rows.slice(0, 8)} />
        {rows.length > 8 && <p style={{ margin: "12px 0 0" }}><a href="/applications">View all</a></p>}
      </div>
    </Shell>
  );
}
