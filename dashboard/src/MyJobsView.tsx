// Saved jobs and an application tracker, stored in this browser only.
import { useMemo, useState } from "react";
import { place, relativeDate } from "./format";
import { myJobs, STATUS_LABELS, TrackedJob, TrackStatus, useTracked } from "./store";
import { ShareButton } from "./actions";

type Filter = "all" | TrackStatus;
const STATUSES = Object.keys(STATUS_LABELS) as TrackStatus[];

function csvCell(value: string) {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function downloadCsv(rows: TrackedJob[]) {
  const header = ["Title", "Company", "Location", "Status", "Saved on", "Applied on", "Note", "Apply link", "FirstOffer link"];
  const lines = rows.map((r) => [
    r.job.title, r.job.company, place(r.job), STATUS_LABELS[r.status], r.saved_at.slice(0, 10),
    r.applied_at?.slice(0, 10) || "", r.note, r.job.apply_url, `${window.location.origin}/job/${r.job.id}`,
  ].map(csvCell).join(","));
  const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "firstoffer-my-jobs.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

export default function MyJobsView() {
  const tracked = useTracked();
  const [filter, setFilter] = useState<Filter>("all");
  const all = useMemo(
    () => Object.values(tracked).sort((a, b) => (b.applied_at || b.saved_at).localeCompare(a.applied_at || a.saved_at)),
    [tracked],
  );
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: all.length };
    for (const t of all) c[t.status] = (c[t.status] || 0) + 1;
    return c;
  }, [all]);
  const shown = filter === "all" ? all : all.filter((t) => t.status === filter);

  if (all.length === 0) {
    return (
      <div className="page">
        <div className="empty-state">
          <p className="empty-icon" aria-hidden="true">☆</p>
          <h2>No saved jobs yet</h2>
          <p className="muted">
            Tap <strong>☆ Save</strong> on any job to keep it here. After you apply, mark it as applied and track
            interviews and offers in one place. Your list stays in this browser; nobody else can see it.
          </p>
          <a className="apply" href="#jobs">Browse jobs</a>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="myjobs-head">
        <div>
          <h2>My jobs</h2>
          <p className="muted small">Saved in this browser only. Export a copy to keep it safe.</p>
        </div>
        <button className="details-button" onClick={() => downloadCsv(all)}>Export CSV</button>
      </div>

      <div className="presets" role="tablist" aria-label="Filter by status">
        {(["all", ...STATUSES] as Filter[]).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "chip on" : "chip"}
            onClick={() => setFilter(f)} disabled={f !== "all" && !counts[f]}>
            {f === "all" ? "All" : STATUS_LABELS[f]} {counts[f] ? `(${counts[f]})` : ""}
          </button>
        ))}
      </div>

      <ul className="job-list">
        {shown.map((t) => (
          <li key={t.job.id} className="job-card tracked-card">
            <div className="job-main">
              <a className="job-title" href={`/job/${t.job.id}`}>{t.job.title}</a>
              <p className="job-company">{t.job.company} · <span className="meta-soft">{place(t.job)}</span></p>
              <p className="job-foot">
                <span>Saved {relativeDate(t.saved_at)?.toLowerCase()}</span>
                {t.applied_at && <span>· Applied {relativeDate(t.applied_at)?.toLowerCase()}</span>}
              </p>
              <input className="note-input" type="text" placeholder="Add a note — referral, interview date, contact…"
                defaultValue={t.note} maxLength={300} onBlur={(e) => myJobs.setNote(t.job.id, e.target.value.trim())}
                aria-label={`Note for ${t.job.title}`} />
            </div>
            <div className="job-actions">
              <select className={`status-select status-${t.status}`} value={t.status}
                onChange={(e) => myJobs.setStatus(t.job, e.target.value as TrackStatus)} aria-label="Status">
                {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
              </select>
              <a className="details-button center" href={t.job.apply_url} target="_blank" rel="noopener noreferrer">Careers page ↗</a>
              <div className="job-actions-row">
                <ShareButton job={t.job} compact />
                <button className="save-button" onClick={() => myJobs.remove(t.job.id)} title="Remove from My jobs">
                  <span aria-hidden="true">🗑</span><span className="sr-only">Remove</span>
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
