import { useCallback, useEffect, useRef, useState } from "react";
import { api, EMPTY_QUERY, FilterOptions, JobQuery, JobSummary, paramsToQuery, queryToParams } from "./api";
import { formatCount, FRESHER_LEVELS } from "./format";
import Filters from "./Filters";
import JobCard from "./JobCard";
import JobDetailPanel from "./JobDetailPanel";
import { copyText } from "./share";
import { toast } from "./toast";

const PAGE_SIZE = 30;

interface Preset {
  label: string;
  apply: (q: JobQuery) => JobQuery;
  active: (q: JobQuery) => boolean;
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((v) => b.includes(v));

const PRESETS: Preset[] = [
  {
    label: "Freshers & interns",
    apply: (q) => ({ ...q, experience: FRESHER_LEVELS, it_only: true }),
    active: (q) => sameSet(q.experience, FRESHER_LEVELS) && q.it_only,
  },
  { label: "Remote", apply: (q) => ({ ...q, remote: !q.remote }), active: (q) => q.remote },
  {
    label: "Posted this week",
    apply: (q) => ({ ...q, posted_within_days: q.posted_within_days === 7 ? null : 7 }),
    active: (q) => q.posted_within_days === 7,
  },
  {
    label: "India",
    apply: (q) => ({ ...q, country: q.country.includes("India") ? q.country.filter((c) => c !== "India") : [...q.country, "India"] }),
    active: (q) => q.country.includes("India"),
  },
];

function readUrl(): JobQuery {
  return paramsToQuery(new URLSearchParams(window.location.search));
}

export default function JobsView() {
  const [query, setQuery] = useState<JobQuery>(readUrl);
  const [searchText, setSearchText] = useState(query.q);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.filters().then(setOptions).catch(() => setOptions(null));
    const onPop = () => {
      const next = readUrl();
      setQuery(next);
      setSearchText(next.q);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Keep the URL in step with the filters so a search can be bookmarked or shared.
  useEffect(() => {
    const params = queryToParams(query).toString();
    const url = `${window.location.pathname}${params ? `?${params}` : ""}${window.location.hash}`;
    if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      window.history.replaceState(null, "", url);
    }
  }, [query]);

  // Debounce typing in the search box.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery((q) => (q.q === searchText ? q : { ...q, q: searchText })), 350);
    return () => window.clearTimeout(timer);
  }, [searchText]);

  const load = useCallback((q: JobQuery, offset: number) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    api
      .jobs(q, offset, PAGE_SIZE, controller.signal)
      .then((page) => {
        setTotal(page.total);
        setJobs((current) => (offset === 0 ? page.items : [...current, ...page.items]));
      })
      .catch((e: unknown) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (abortRef.current === controller) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load(query, 0);
  }, [query, load]);

  // "/" jumps to the search box, as on many sites.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) && !target.isContentEditable) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const shareSearch = async () => {
    const params = queryToParams(query).toString();
    const url = `${window.location.origin}/${params ? `?${params}` : ""}`;
    const touch = window.matchMedia("(pointer: coarse)").matches;
    if (touch && navigator.share) {
      try {
        await navigator.share({ title: "FirstOffer jobs", url });
        return;
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
      }
    }
    toast((await copyText(url)) ? "Link to this search copied" : `Couldn't copy; the link is ${url}`);
  };

  const update = (next: JobQuery) => setQuery(next);
  const activeFilterCount =
    query.experience.length + query.category.length + query.country.length + query.company.length +
    (query.it_only ? 1 : 0) + (query.remote ? 1 : 0) + (query.posted_within_days ? 1 : 0);

  return (
    <div className="jobs-layout">
      <aside className={filtersOpen ? "sidebar open" : "sidebar"} aria-label="Filters">
        <div className="sidebar-head">
          <h2>Filters</h2>
          <button className="link-button" onClick={() => { setSearchText(""); update(EMPTY_QUERY); }} disabled={activeFilterCount === 0 && !query.q}>
            Clear all
          </button>
          <button className="icon-button close-filters" onClick={() => setFiltersOpen(false)} aria-label="Close filters">✕</button>
        </div>
        <Filters query={query} options={options} onChange={update} />
      </aside>
      {filtersOpen && <div className="scrim" onClick={() => setFiltersOpen(false)} />}

      <section className={loading ? "results loading" : "results"} aria-busy={loading}>
        <div className="search-row">
          <input
            ref={searchRef}
            type="search"
            className="search"
            placeholder="Search title, skill, company or city — e.g. “java developer pune”"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            aria-label="Search jobs"
          />
          <button className="filters-toggle" onClick={() => setFiltersOpen(true)}>
            Filters{activeFilterCount ? ` (${activeFilterCount})` : ""}
          </button>
        </div>

        <div className="presets" role="group" aria-label="Quick filters">
          {PRESETS.map((p) => {
            const on = p.active(query);
            return (
              <button key={p.label} className={on ? "chip on" : "chip"} aria-pressed={on}
                onClick={() => update(on && p.label === "Freshers & interns" ? { ...query, experience: [], it_only: false } : p.apply(query))}>
                {p.label}
              </button>
            );
          })}
        </div>

        <div className="results-head">
          <p className="count" aria-live="polite">
            {total === null || (loading && jobs.length === 0)
              ? "Loading jobs…"
              : `${formatCount(total)} ${total === 1 ? "opening" : "openings"}${loading ? " · updating…" : ""}`}
          </p>
          <button className="link-button share-search" onClick={shareSearch}>Share this search</button>
          <label className="sort">
            Sort
            <select value={query.sort} onChange={(e) => update({ ...query, sort: e.target.value as JobQuery["sort"] })}>
              <option value="newest">Newest posted</option>
              <option value="first_seen">Recently added here</option>
            </select>
          </label>
        </div>

        {error && <div className="notice error">Couldn't load jobs: {error}. Is the API running?</div>}
        {!error && total === 0 && !loading && (
          <div className="notice">
            No jobs match these filters. Try removing a filter, or check the <a href="#companies">Companies</a> tab for
            careers pages we can't track automatically.
          </div>
        )}

        <ul className="job-list">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} selected={job.id === selectedId} onOpen={() => setSelectedId(job.id)} />
          ))}
        </ul>

        {total !== null && jobs.length < total && (
          <button className="load-more" onClick={() => load(query, jobs.length)} disabled={loading}>
            {loading ? "Loading…" : `Show more (${formatCount(total - jobs.length)} left)`}
          </button>
        )}
        {loading && jobs.length === 0 && <div className="skeletons">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton" />)}</div>}
      </section>

      {selectedId !== null && <JobDetailPanel id={selectedId} onClose={() => setSelectedId(null)} onOpen={setSelectedId} />}
    </div>
  );
}
