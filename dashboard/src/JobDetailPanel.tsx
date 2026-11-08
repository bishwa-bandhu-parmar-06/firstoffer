import { useEffect, useState } from "react";
import { api, JobDetail } from "./api";
import JobDetailBody from "./JobDetail";

export default function JobDetailPanel({ id, onClose, onOpen }: { id: number; onClose: () => void; onOpen: (id: number) => void }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    api.job(id).then(setJob).catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="scrim detail-scrim" onClick={onClose} />
      <aside className="detail" role="dialog" aria-modal="true" aria-label={job ? job.title : "Job details"}>
        <div className="detail-top">
          <a className="link-button" href={`/job/${id}`} target="_blank" rel="noopener">Open full page ↗</a>
          <button className="icon-button" onClick={onClose} aria-label="Close details">✕</button>
        </div>
        {error && <div className="notice error">Couldn't load this job: {error}</div>}
        {!job && !error && <div className="skeleton tall" />}
        {job && <JobDetailBody job={job} onOpenSimilar={onOpen} />}
      </aside>
    </>
  );
}
