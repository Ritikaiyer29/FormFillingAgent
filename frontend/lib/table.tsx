"use client";
import { CALL_LABEL, STATE_LABEL } from "./shell";

export function ApplicationsTable({ rows }: { rows: any[] }) {
  if (!rows.length) return <p className="empty">No applications yet. Enter a mobile number above and place a call.</p>;
  return (
    <table>
      <thead><tr><th>Mobile</th><th>Candidate</th><th>Form</th><th>Status</th><th>Call</th><th>Started</th><th /></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id}>
          <td>{r.phone}</td>
          <td>{r.candidate_name || <span className="empty">-</span>}</td>
          <td>{r.variant === "ITI" ? "ITI (Form-A)" : r.variant === "VOCATIONAL" ? "Vocational (Form-B)" : <span className="empty">Not chosen</span>}</td>
          <td><span className={`badge ${r.state === "submitted" ? "ok" : r.state === "draft" ? "" : "live"}`}>{STATE_LABEL[r.state] || r.state}</span></td>
          <td>{CALL_LABEL[r.call_status] || r.call_status}</td>
          <td>{new Date(r.created_at).toLocaleString()}</td>
          <td><a href={`/session?id=${r.id}`}>Open</a></td>
        </tr>))}
      </tbody>
    </table>
  );
}
