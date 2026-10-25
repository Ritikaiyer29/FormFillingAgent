"use client";
import { useEffect, useRef } from "react";

// The server sends what to draw and where, in a 827 x 1169 page space, so the screen and the PDF always agree.
const W = 827;
const H = 1169;

function Op({ o, fresh }: { o: any; fresh: boolean }) {
  const [x, y, w, h] = o.box;
  const style: any = { left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%`, width: `${(w / W) * 100}%`, height: `${(h / H) * 100}%` };
  const cls = `op ${o.kind}${fresh ? " fresh" : ""}${o.status === "confirmed" ? " ok" : ""}`;
  if (o.kind === "tick") {
    return <div className={cls} style={style}><svg viewBox="0 0 24 24" preserveAspectRatio="xMidYMid meet"><polyline points="3,13 9,20 21,4" /></svg></div>;
  }
  if (o.kind === "ring") return <div className={cls} style={style} />;
  style.fontSize = `${(o.size / W) * 100}cqw`;
  style.textAlign = o.align === "c" ? "center" : "left";
  style.justifyContent = o.lines.length > 1 ? "flex-start" : "center";
  return <div className={cls} style={style} data-path={o.path}>{o.lines.map((l: string, i: number) => <span key={i}>{l}</span>)}</div>;
}

export function FormPaper({ snap, fresh }: { snap: any; fresh: Record<string, boolean> }) {
  const pages: string[] = snap.form?.pages || [];
  const ops: any[] = snap.form?.ops || [];
  const root = useRef<HTMLDivElement>(null);
  const hasFresh = Object.keys(fresh).length > 0;

  // Bring the newest answer into view so the operator watches it being written.
  useEffect(() => {
    if (!hasFresh) return;
    const el = root.current?.querySelector(".op.fresh");
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [hasFresh, snap.revision]);

  return (
    <div className="papers" ref={root}>
      {pages.map((name, pi) => (
        <div className="paper" key={name}>
          <img src={`/form/${name}.jpg`} alt={`Form page ${pi + 1}`} draggable={false} />
          {ops.filter((o) => o.page === pi).map((o, i) => <Op key={`${o.path}-${o.kind}-${i}`} o={o} fresh={!!fresh[String(o.path).split(".")[0]]} />)}
        </div>
      ))}
    </div>
  );
}
