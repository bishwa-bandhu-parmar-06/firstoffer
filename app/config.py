from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./jobs.db"
    # Default hours between polls of one source; a source can override it with "interval_hours".
    poll_interval_hours: float = 3
    # How often the scheduler wakes up to poll whichever sources are due.
    scheduler_tick_minutes: int = 15
    request_timeout_seconds: float = 30
    # Minimum gap between two requests to the same host, so we never hammer a careers site.
    min_request_interval_seconds: float = 1.0
    http_retries: int = 3
    max_concurrent_sources: int = 4
    max_jobs_per_source: int = 25000
    # Full job descriptions fetched per source per run, for platforms whose list omits them.
    detail_fetches_per_run: int = 300
    # A job is marked closed after it is missing from this many complete polls in a row.
    missed_runs_before_inactive: int = 2
    # Required in the X-Admin-Token header for /admin endpoints; admin endpoints are disabled while empty.
    admin_token: str = ""
    brand_name: str = "FirstOffer"  # shown in the Telegram digest and alerts
    user_agent: str = "FirstOfferBot/1.0 (aggregates public job listings; polite polling)"
    # False = "lite storage" for small free databases: descriptions are read to detect the experience
    # level, then dropped (the dashboard links to the company page for the full text).
    store_descriptions: bool = True
    # Closed jobs are deleted this many days after they were last seen (0 = keep forever).
    prune_closed_after_days: int = 30
    # Telegram digest. Without a token and chat id the digest only runs as a dry run (printed, nothing sent).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""  # "@your_channel" or a numeric group id like "-1001234567890"
    digest_experience: str = "intern,fresher,junior"
    digest_countries: str = ""  # optional comma list, e.g. "India"; empty = everywhere
    digest_max_jobs: int = 40  # per digest; the rest are summarized with a link to the dashboard
    digest_max_age_hours: int = 24  # never announce jobs first seen longer ago than this
    digest_minute: int = 5  # minute past each hour when the digest goes out
    dashboard_url: str = ""  # public dashboard address, linked from the digest when set
    # Public Telegram channel link shown as a "Join on Telegram" button on the site (empty = no button).
    telegram_channel_url: str = "https://t.me/firstoffer_jobs"
    # Where to send "a source keeps failing" alerts: your own chat id with the bot, or a private group.
    # Empty = no alerts. Use a different chat than the public channel.
    alert_chat_id: str = ""
    alert_after_failures: int = 3
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
