import { useEffect, useState } from "react";
import { api, SiteInfo, Stats } from "./api";
import { formatCount } from "./format";
import JobsView from "./JobsView";
import JobPage from "./JobPage";
import MyJobsView from "./MyJobsView";
import CompaniesView from "./CompaniesView";
import SourcesView from "./SourcesView";
import { useTracked } from "./store";
import { Toaster } from "./toast";

type Tab = "jobs" | "my" | "companies" | "sources";
const NAV: { id: Tab; label: string }[] = [
  { id: "jobs", label: "Jobs" },
  { id: "my", label: "My jobs" },
  { id: "companies", label: "Companies" },
];
const ALL_TABS: Tab[] = ["jobs", "my", "companies", "sources"];

// Tabs live in the hash (#companies) so the query string stays free for job filters.
function tabFromHash(): Tab {
  const hash = window.location.hash.replace("#", "") as Tab;
  return ALL_TABS.includes(hash) ? hash : "jobs";
}

/** The job id when the page is a shared job link (/job/123). */
function jobIdFromPath(): number | null {
  const match = window.location.pathname.match(/^\/job\/(\d+)\/?$/);
  return match ? Number(match[1]) : null;
}

type Theme = "light" | "dark" | null;
const THEME_KEY = "firstoffer.theme";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = window.localStorage.getItem(THEME_KEY);
      return saved === "light" || saved === "dark" ? saved : null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      if (theme) window.localStorage.setItem(THEME_KEY, theme);
      else window.localStorage.removeItem(THEME_KEY);
    } catch {
      // storage blocked: the choice lasts for this visit
    }
  }, [theme]);
  const toggle = () => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const current = theme || (systemDark ? "dark" : "light");
    setTheme(current === "dark" ? "light" : "dark");
  };
  return [theme, toggle];
}

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [jobId] = useState<number | null>(jobIdFromPath);
  const [stats, setStats] = useState<Stats | null>(null);
  const [site, setSite] = useState<SiteInfo | null>(null);
  const [theme, toggleTheme] = useTheme();
  const trackedCount = Object.keys(useTracked()).length;

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null));
    api.site().then(setSite).catch(() => setSite(null));
  }, []);

  const showCompany = (company: string) => {
    window.history.pushState(null, "", `?company=${encodeURIComponent(company)}#jobs`);
    setTab("jobs");
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  // On a job page the tabs are links back to the main page.
  const tabHref = (t: Tab) => (jobId === null ? `#${t}` : `/#${t}`);
  const isDark = theme === "dark" || (theme === null && window.matchMedia("(prefers-color-scheme: dark)").matches);

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">FO</span>
          <div>
            <span className="brand-name">FirstOffer</span>
            <p className="tagline">
              Fresher IT jobs straight from company careers pages
              {stats && ` · ${formatCount(stats.active_jobs)} postings, ${stats.companies_with_jobs} companies`}
            </p>
          </div>
        </a>
        <div className="topbar-right">
          <nav className="tabs" aria-label="Sections">
            {NAV.map((t) => {
              const active = jobId === null && tab === t.id;
              return (
                <a key={t.id} href={tabHref(t.id)} className={active ? "tab active" : "tab"} aria-current={active ? "page" : undefined}>
                  {t.label}
                  {t.id === "my" && trackedCount > 0 && <span className="tab-count">{trackedCount}</span>}
                </a>
              );
            })}
          </nav>
          {site?.telegram_channel_url && (
            <a className="telegram-button small-btn" href={site.telegram_channel_url} target="_blank" rel="noopener noreferrer">
              <span aria-hidden="true">✈</span> <span className="hide-narrow">Join</span> Telegram
            </a>
          )}
          <button className="icon-button theme-toggle" onClick={toggleTheme}
            aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"} title={isDark ? "Light theme" : "Dark theme"}>
            {isDark ? "☀" : "☾"}
          </button>
        </div>
      </header>
      <main>
        {jobId !== null ? (
          <JobPage id={jobId} telegramUrl={site?.telegram_channel_url ?? null} />
        ) : (
          <>
            {tab === "jobs" && <JobsView />}
            {tab === "my" && <MyJobsView />}
            {tab === "companies" && <CompaniesView onShowCompany={showCompany} />}
            {tab === "sources" && <SourcesView />}
          </>
        )}
      </main>
      <footer className="footer">
        <p>
          <strong>FirstOffer</strong> lists jobs from companies' own careers sites. You always apply on the company's site;
          FirstOffer never charges candidates.
        </p>
        <p className="footer-links">
          {site?.telegram_channel_url && <a href={site.telegram_channel_url} target="_blank" rel="noopener noreferrer">Telegram channel</a>}
          <a href={tabHref("companies")}>Companies we track</a>
          <a href={tabHref("sources")}>Source status</a>
        </p>
      </footer>
      <Toaster />
    </div>
  );
}
