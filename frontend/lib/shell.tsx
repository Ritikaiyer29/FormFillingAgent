"use client";
import { useEffect, useState } from "react";
import { api, getKey, setKey } from "./api";

export const STATE_LABEL: Record<string, string> = {
  draft: "Not started", collecting: "In progress", ready_for_submission: "Ready to submit", submitted: "Submitted",
};
export const CALL_LABEL: Record<string, string> = {
  not_started: "Not called", dialing: "Calling", in_progress: "On call", completed: "Call finished",
  failed: "Call failed", busy: "Line busy", no_answer: "Not answered",
};

function SignIn({ onDone, failed }: { onDone: () => void; failed: boolean }) {
  const [key, setK] = useState("");
  return (
    <div className="center">
      <div className="card signin">
        <div className="brand"><div className="mark">A</div><div>Apprentice Desk<small>Voice application assistant</small></div></div>
        <form onSubmit={(e) => { e.preventDefault(); setKey(key.trim()); onDone(); }}>
          <label>Access key<input type="password" autoFocus value={key} onChange={(e) => setK(e.target.value)} /></label>
          {failed && <p className="err" style={{ margin: 0 }}>That key was not accepted. Please check it and try again.</p>}
          <button className="primary" type="submit" disabled={!key.trim()}>Sign in</button>
        </form>
      </div>
    </div>
  );
}

export function Shell({ title, active, top, children }: { title: string; active: "calls" | "applications"; top?: React.ReactNode; children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "in" | "out">("checking");
  const [failed, setFailed] = useState(false);

  const check = async () => {
    if (!getKey()) { setStatus("out"); return; }
    try { await api("/api/sessions"); setStatus("in"); setFailed(false); }
    catch (e: any) { setStatus("out"); setFailed(e.status === 401); }
  };
  useEffect(() => { check(); }, []);

  if (status === "checking") return <div className="center"><span className="empty">Loading...</span></div>;
  if (status === "out") return <SignIn failed={failed} onDone={check} />;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><div className="mark">A</div><div>Apprentice Desk<small>HAL Kanpur</small></div></div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav">
          <a href="/" className={active === "calls" ? "on" : ""}>Calls</a>
          <a href="/applications" className={active === "applications" ? "on" : ""}>Applications</a>
        </nav>
        <div className="grow" />
        <button className="ghost" onClick={() => { setKey(""); setStatus("out"); }}>Sign out</button>
      </aside>
      <div className="main">
        <header className="top"><h1>{title}</h1>{top}</header>
        <div className="content">{children}</div>
      </div>
    </div>
  );
}
