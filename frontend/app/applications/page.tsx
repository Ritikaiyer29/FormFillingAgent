"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Shell } from "../../lib/shell";
import { ApplicationsTable } from "../../lib/table";

export default function Applications() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api("/api/sessions").then(setRows).catch(() => {}); }, []);
  return (
    <Shell title="Applications" active="applications">
      <div className="card"><ApplicationsTable rows={rows} /></div>
    </Shell>
  );
}
