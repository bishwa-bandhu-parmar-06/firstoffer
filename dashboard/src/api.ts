// Typed client for the FastAPI backend. Paths are relative: in development Vite proxies them,
// in production FastAPI serves this dashboard itself.

export interface JobSummary {
  id: number;
  company: string;
  title: string;
  location: string | null;
  city: string | null;
  country: string | null;
  is_remote: boolean | null;
  experience_level: string | null;
  experience_years: number | null;
  category: string | null;
  employment_type: string | null;
  workplace_type: string | null;
  department: string | null;
  apply_url: string;
  posted_at: string | null;
  first_seen_at: string;
  source_provider: string;
  similar_count: number;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  active: boolean;
  last_seen_at: string;
  similar_postings: { id: number; location: string | null; apply_url: string }[];
}

export interface JobPage {
  total: number;
  limit: number;
  offset: number;
  items: JobSummary[];
}

export interface Option {
  value: string;
  label?: string;
  count: number;
  is_it?: boolean;
}

export interface FilterOptions {
  experience: Option[];
  categories: Option[];
  countries: Option[];
  companies: Option[];
  remote_count: number;
}

export interface CompaniesResponse {
  collected: { company: string; active_jobs: number }[];
  link_only: { company: string; careers_url: string; fresher_url?: string; reason: string }[];
}

export interface SourceHealth {
  key: string;
  company: string;
  provider: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_job_count: number;
  complete_listing: boolean;
  consecutive_failures: number;
  last_error: string | null;
}

export interface Stats {
  total_jobs: number;
  active_jobs: number;
  companies_with_jobs: number;
}

/** Filter state shared by the URL, the sidebar and the API query. Lists are comma-joined in the URL. */
export interface JobQuery {
  q: string;
  experience: string[];
  category: string[];
  it_only: boolean;
  country: string[];
  company: string[];
  remote: boolean;
  posted_within_days: number | null;
  sort: "newest" | "first_seen";
}

export const EMPTY_QUERY: JobQuery = {
  q: "",
  experience: [],
  category: [],
  it_only: false,
  country: [],
  company: [],
  remote: false,
  posted_within_days: null,
  sort: "newest",
};

export function queryToParams(query: JobQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.q.trim()) params.set("q", query.q.trim());
  for (const key of ["experience", "category", "country", "company"] as const) {
    if (query[key].length) params.set(key, query[key].join(","));
  }
  if (query.it_only) params.set("it_only", "true");
  if (query.remote) params.set("remote", "true");
  if (query.posted_within_days) params.set("posted_within_days", String(query.posted_within_days));
  if (query.sort !== "newest") params.set("sort", query.sort);
  return params;
}

export function paramsToQuery(params: URLSearchParams): JobQuery {
  const list = (key: string) => (params.get(key) || "").split(",").map((v) => v.trim()).filter(Boolean);
  const days = Number(params.get("posted_within_days"));
  return {
    q: params.get("q") || "",
    experience: list("experience"),
    category: list("category"),
    it_only: params.get("it_only") === "true",
    country: list("country"),
    company: list("company"),
    remote: params.get("remote") === "true",
    posted_within_days: Number.isFinite(days) && days > 0 ? days : null,
    sort: params.get("sort") === "first_seen" ? "first_seen" : "newest",
  };
}

async function get<T>(path: string, params?: URLSearchParams, signal?: AbortSignal): Promise<T> {
  const url = params && [...params].length ? `${path}?${params}` : path;
  const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export const api = {
  jobs(query: JobQuery, offset: number, limit: number, signal?: AbortSignal) {
    const params = queryToParams(query);
    params.set("offset", String(offset));
    params.set("limit", String(limit));
    return get<JobPage>("/jobs", params, signal);
  },
  job: (id: number) => get<JobDetail>(`/jobs/${id}`),
  filters: () => get<FilterOptions>("/filters"),
  companies: () => get<CompaniesResponse>("/companies"),
  sources: () => get<SourceHealth[]>("/sources"),
  stats: () => get<Stats>("/stats"),
  site: () => get<SiteInfo>("/site"),
};

export interface SiteInfo {
  brand_name: string;
  telegram_channel_url: string | null;
}
