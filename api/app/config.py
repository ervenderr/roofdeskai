from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    local_llm_url: str = "http://host.docker.internal:11434/v1"
    local_llm_model: str = "llama3.1:8b"
    embed_model: str = "all-minilm"
    admin_api_key: str = ""  # empty disables every admin endpoint
    escalation_webhook_url: str = ""
    public_url: str = "http://localhost:8000"
    # --- outbound outreach ---
    mailpit_url: str = "http://mailpit:8025"
    sender_name: str = "The LeadPilot team"
    sender_email: str = "hello@leadpilot.example"
    sender_address: str = ""  # physical address for the email footer (required to send); set SENDER_ADDRESS
    offer_summary: str = "an AI assistant that answers customer enquiries instantly, qualifies them and books appointments"
    outreach_enforce_window: bool = True
    outreach_send_hours: str = "9-17"  # local hours, weekdays only
    outreach_timezone: str = "Asia/Manila"
    groq_api_key: str = ""
    nvidia_api_key: str = ""
    openrouter_api_key: str = ""
    prompts_dir: Path = Path("/srv/prompts")
    max_message_chars: int = 2000
    chat_rate_per_min: int = 20  # per client IP, in-process (single instance)
    llm_timeout_s: float = 60
    provider_cooldown_s: float = 60


settings = Settings()
