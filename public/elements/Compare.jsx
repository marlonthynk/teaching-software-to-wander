// Compare mode: the Records and Graph answers to one question, side by side.
// app.py sends `props` and updates them while both agents work:
//   sides: [{ key, label, hint, status, text, steps: [{ title, detail, running, error }],
//             started, metrics: { calls, input_tokens, output_tokens, seconds, hit_cap }, error }]
//   only:  { records: [{ name, kind }], graph: [...] } once both have finished, else null
import { useEffect, useState } from "react";
import { Markdown } from "@/components/markdown";

const STATUS = { thinking: "Thinking…", looking: "Looking…", writing: "Writing…", done: "Done", error: "Failed" };

function useNow(active) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

const seconds = (side, now) =>
  side.metrics ? side.metrics.seconds : side.started ? (now - side.started) / 1000 : 0;
const tokens = (side) => (side.metrics ? side.metrics.input_tokens + side.metrics.output_tokens : null);

function Steps({ steps }) {
  if (!steps.length) return null;
  return (
    <details className="wc-steps">
      <summary>What it looked at ({steps.length} tool call{steps.length === 1 ? "" : "s"})</summary>
      <ol>
        {steps.map((s, i) => (
          <li key={i} className={s.error ? "wc-step wc-step-error" : "wc-step"}>
            {s.running ? (
              <span className="wc-step-title wc-running">{s.title}</span>
            ) : (
              <details>
                <summary className="wc-step-title">{s.title}</summary>
                <pre>{s.detail}</pre>
              </details>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

function Side({ side, only }) {
  const busy = side.status !== "done" && side.status !== "error";
  return (
    <section className={`wc-side wc-${side.key}`} aria-busy={busy}>
      <header className="wc-head">
        <span className="wc-dot" aria-hidden="true" />
        <span className="wc-label">{side.label}</span>
        <span className="wc-hint">{side.hint}</span>
        <span className={`wc-status wc-status-${side.status}`}>
          {STATUS[side.status]}
          {busy && side.steps.length ? ` (${side.steps.length})` : ""}
        </span>
      </header>
      <Steps steps={side.steps} />
      <div className="wc-answer">
        {side.error ? (
          <p className="wc-error">{side.error}</p>
        ) : side.text ? (
          <Markdown>{side.text}</Markdown>
        ) : (
          <p className="wc-waiting">{busy ? "No answer yet." : "No answer."}</p>
        )}
      </div>
      {only && (
        <div className="wc-only">
          <span className="wc-only-label">Only in this answer</span>
          {only.length ? (
            only.map((t) => (
              <span key={t.name} className="wc-chip" title={t.kind}>
                {t.name}
                <span className="wc-chip-kind">{t.kind.toLowerCase()}</span>
              </span>
            ))
          ) : (
            <span className="wc-only-none">nothing the other doesn't name</span>
          )}
        </div>
      )}
    </section>
  );
}

function Work({ sides, now }) {
  const rows = [
    ["Tool calls", (s) => (s.metrics ? s.metrics.calls : s.steps.length), (v) => String(v)],
    ["Tokens", tokens, (v) => (v == null ? "…" : v.toLocaleString())],
    ["Time", (s) => seconds(s, now), (v) => `${Math.round(v)}s`],
  ];
  return (
    <div className="wc-work" role="table" aria-label="The work each side did">
      {rows.map(([label, get, show]) => {
        const values = sides.map(get);
        const top = Math.max(1, ...values.map((v) => v || 0));
        return (
          <div className="wc-work-row" role="row" key={label}>
            <span className="wc-work-label" role="rowheader">{label}</span>
            {sides.map((s, i) => (
              <span className={`wc-work-cell wc-${s.key}`} role="cell" key={s.key}>
                <span className="wc-bar" style={{ width: `${((values[i] || 0) / top) * 100}%` }} />
                <span className="wc-work-value">
                  {s.label} {show(values[i])}
                  {label === "Tool calls" && s.metrics && s.metrics.hit_cap ? " (hit the limit)" : ""}
                </span>
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export default function Compare() {
  const sides = props.sides || [];
  const busy = sides.some((s) => s.status !== "done" && s.status !== "error");
  const now = useNow(busy);
  return (
    <div className="wander-compare">
      <div className="wc-columns">
        {sides.map((s) => (
          <Side key={s.key} side={s} only={props.only ? props.only[s.key] || [] : null} />
        ))}
      </div>
      <Work sides={sides} now={now} />
    </div>
  );
}
