// Buttons shared by job cards, the detail panel and the job page: Apply, Save and Share.
import { useEffect, useRef, useState } from "react";
import { JobSummary } from "./api";
import { copyText, jobUrl, shareTargets, shareText } from "./share";
import { myJobs, STATUS_LABELS, useTrackedJob } from "./store";
import { toast } from "./toast";

/** Opens the company's careers page, then offers to add the job to "My jobs" as applied. */
export function ApplyButton({ job, wide = false, label }: { job: JobSummary; wide?: boolean; label?: string }) {
  const tracked = useTrackedJob(job.id);
  const alreadyApplied = tracked && tracked.status !== "saved";
  const onClick = () => {
    if (alreadyApplied) return;
    // Shown when they come back from the careers site.
    window.setTimeout(() => {
      toast(`Applied to ${job.title}?`, { label: "Mark as applied", run: () => myJobs.setStatus(job, "applied") }, 15000);
    }, 600);
  };
  return (
    <a className={wide ? "apply wide" : "apply"} href={job.apply_url} target="_blank" rel="noopener noreferrer" onClick={onClick}>
      {label || "Apply"} <span aria-hidden="true">↗</span>
    </a>
  );
}

export function SaveButton({ job, compact = false }: { job: JobSummary; compact?: boolean }) {
  const tracked = useTrackedJob(job.id);
  const label = tracked ? STATUS_LABELS[tracked.status] : "Save";
  const onClick = () => {
    if (tracked && tracked.status !== "saved") {
      toast(`Already in My jobs as “${STATUS_LABELS[tracked.status]}”`);
      return;
    }
    const saved = myJobs.toggleSaved(job);
    toast(saved ? "Saved to My jobs" : "Removed from My jobs");
  };
  return (
    <button className={tracked ? "save-button on" : "save-button"} onClick={onClick} aria-pressed={Boolean(tracked)}
      title={tracked ? "In My jobs" : "Save to My jobs"}>
      <span aria-hidden="true">{tracked ? "★" : "☆"}</span>
      {compact ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </button>
  );
}

/** Uses the phone's share sheet when there is one, otherwise a menu of apps plus "Copy link". */
export function ShareButton({ job, compact = false }: { job: JobSummary; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const url = jobUrl(job.id);
  const text = shareText(job);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const onClick = async () => {
    const touch = window.matchMedia("(pointer: coarse)").matches;
    if (touch && navigator.share) {
      try {
        await navigator.share({ title: `${job.title} at ${job.company}`, text, url });
        return;
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
      }
    }
    setOpen((o) => !o);
  };

  const copy = async () => {
    setOpen(false);
    toast((await copyText(url)) ? "Link copied — paste it anywhere" : "Couldn't copy; the link is " + url);
  };

  return (
    <div className="share" ref={ref}>
      <button className="share-button" onClick={onClick} aria-haspopup="menu" aria-expanded={open} title="Share this job">
        <span aria-hidden="true">⤴</span>
        {compact ? <span className="sr-only">Share</span> : <span>Share</span>}
      </button>
      {open && (
        <div className="share-menu" role="menu">
          <button role="menuitem" onClick={copy}>Copy link</button>
          {shareTargets(url, text).map((t) => (
            <a key={t.id} role="menuitem" href={t.href} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
              {t.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
