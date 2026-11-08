// "My jobs": jobs a visitor saved or applied to, kept in this browser's localStorage (no accounts).
import { useSyncExternalStore } from "react";
import { JobSummary } from "./api";

export type TrackStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected";

export const STATUS_LABELS: Record<TrackStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Got an offer",
  rejected: "Not selected",
};

export interface TrackedJob {
  job: JobSummary; // snapshot taken when saved, so the list works even after the job closes
  status: TrackStatus;
  saved_at: string;
  applied_at: string | null;
  note: string;
}

const KEY = "firstoffer.myjobs.v1";
type Tracked = Record<string, TrackedJob>;

function read(): Tracked {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

let state: Tracked = read();
const listeners = new Set<() => void>();

function commit(next: Tracked) {
  state = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Private windows or full storage: keep working for this visit only.
  }
  listeners.forEach((l) => l());
}

// Another tab changed the list.
window.addEventListener("storage", (e) => {
  if (e.key === KEY) {
    state = read();
    listeners.forEach((l) => l());
  }
});

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTracked(): Tracked {
  return useSyncExternalStore(subscribe, () => state);
}

export function useTrackedJob(id: number): TrackedJob | undefined {
  return useSyncExternalStore(subscribe, () => state[id]);
}

const now = () => new Date().toISOString();

/** Pick only the summary fields, so a full JobDetail (with its description) isn't stored. */
function snapshot(job: JobSummary): JobSummary {
  const { id, company, title, location, city, country, is_remote, experience_level, experience_years, category,
    employment_type, workplace_type, department, apply_url, posted_at, first_seen_at, source_provider, similar_count } = job;
  return { id, company, title, location, city, country, is_remote, experience_level, experience_years, category,
    employment_type, workplace_type, department, apply_url, posted_at, first_seen_at, source_provider, similar_count };
}

export const myJobs = {
  toggleSaved(job: JobSummary) {
    const next = { ...state };
    if (next[job.id]) delete next[job.id];
    else next[job.id] = { job: snapshot(job), status: "saved", saved_at: now(), applied_at: null, note: "" };
    commit(next);
    return Boolean(next[job.id]);
  },
  setStatus(job: JobSummary, status: TrackStatus) {
    const current = state[job.id];
    const appliedAt = status === "saved" ? null : current?.applied_at || now();
    commit({
      ...state,
      [job.id]: { job: current?.job || snapshot(job), status, saved_at: current?.saved_at || now(), applied_at: appliedAt, note: current?.note || "" },
    });
  },
  setNote(id: number, note: string) {
    if (state[id]) commit({ ...state, [id]: { ...state[id], note } });
  },
  remove(id: number) {
    const next = { ...state };
    delete next[id];
    commit(next);
  },
};
