from pathlib import Path

from pydantic_settings import BaseSettings


SECRET_HINTS = ("password", "key")


class Settings(BaseSettings):
    def __repr_args__(self):
        """Mask secrets so a failing assert, traceback or log line never prints them."""
        for name, value in super().__repr_args__():
            yield name, "**********" if value and any(h in name for h in SECRET_HINTS) else value

    database_url: str
    local_llm_url: str = "http://host.docker.internal:11434/v1"
    local_llm_model: str = "llama3.1:8b"
    embed_model: str = "all-minilm"
    admin_api_key: str = ""  # empty disables every admin endpoint
    escalation_webhook_url: str = ""
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = []  # sites allowed to call /chat and /pilot-requests from a browser (the demo page)
    owner_email: str = ""  # gets an email when someone asks for a pilot; empty disables it
    # --- scraping (gosom/google-maps-scraper web API) ---
    scraper_url: str = "http://scraper:8080"
    scrape_queries_per_day: int = 30  # be a polite client: Google's terms restrict scraping, so keep volume small
    # --- outbound outreach ---
    mailpit_url: str = "http://mailpit:8025"
    mail_transport: str = "mailpit"  # mailpit (dev) | smtp (your own mailbox; Resend bans cold outreach)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # STARTTLS
    smtp_user: str = ""
    smtp_password: str = ""  # Gmail app password
    imap_host: str = "imap.gmail.com"
    sender_name: str = "The LeadPilot team"
    sender_email: str = "hello@leadpilot.example"
    sender_address: str = ""  # physical address for the email footer (required to send); set SENDER_ADDRESS
    offer_summary: str = "an AI assistant that answers customer enquiries instantly, qualifies them and books appointments"
    # Fixed, true claims only: added by code to the first email so the model cannot invent features.
    service_points: list[str] = [
        "Replies to customer enquiries instantly, even after hours",
        "Asks the right questions and qualifies each lead for you",
        "Books appointments straight into your schedule",
        "Hands the conversation to you when a person is needed",
    ]
    brand_color: str = "#1D5BD8"  # header, bullets and button in the HTML email
    outreach_enforce_window: bool = True
    outreach_send_hours: str = "9-17"  # local hours, weekdays only
    outreach_timezone: str = "Asia/Manila"
    groq_api_key: str = ""
    nvidia_api_key: str = ""
    openrouter_api_key: str = ""
    prompts_dir: Path = Path("/srv/prompts")
    site_dir: Path = Path("/srv/site")
    max_message_chars: int = 2000
    chat_rate_per_min: int = 20  # per client IP, in-process (single instance)
    llm_timeout_s: float = 60
    provider_cooldown_s: float = 60


settings = Settings()
