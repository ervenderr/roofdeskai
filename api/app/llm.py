import logging
import time
from dataclasses import dataclass

from openai import BadRequestError, OpenAI, OpenAIError

from .config import settings

log = logging.getLogger("leadpilot.llm")


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    cooldown_until: float = 0.0


# Priority order. Keyless providers other than local/OVH are skipped. All are OpenAI-compatible.
# Open-weight models only; limits per github.com/mnfst/awesome-free-llm-apis.
PROVIDERS = [
    Provider("local", settings.local_llm_url, "ollama", settings.local_llm_model),
    Provider("groq", "https://api.groq.com/openai/v1", settings.groq_api_key, "openai/gpt-oss-20b"),
    Provider("nvidia", "https://integrate.api.nvidia.com/v1", settings.nvidia_api_key, "openai/gpt-oss-20b"),
    Provider("openrouter", "https://openrouter.ai/api/v1", settings.openrouter_api_key,
             "google/gemma-4-31b-it:free"),
    Provider("ovh", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "anonymous", "gpt-oss-20b"),
]


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, body) for prompts/<name>.md; first line is `version: <v>`."""
    head, _, body = (settings.prompts_dir / f"{name}.md").read_text().partition("\n")
    return head.removeprefix("version:").strip(), body.strip()


def _call(p: Provider, messages: list[dict]) -> dict:
    client = OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=settings.llm_timeout_s, max_retries=0)
    start = time.perf_counter()
    resp = client.chat.completions.create(model=p.model, messages=messages, temperature=0)
    return {
        "content": resp.choices[0].message.content or "",
        "model": f"{p.name}:{p.model}",
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


def chat(messages: list[dict], providers: list[Provider] = PROVIDERS) -> dict:
    """Try providers in order; any API error (429, 5xx, timeout, auth) cools that provider down and moves on."""
    now = time.monotonic()
    for p in providers:
        if not p.api_key or p.cooldown_until > now:
            continue
        try:
            return _call(p, messages)
        except BadRequestError as e:  # this request's fault, not the provider's: try the next one, no cooldown
            log.warning("provider %s rejected the request: %s", p.name, e.status_code)
        except OpenAIError as e:
            p.cooldown_until = time.monotonic() + settings.provider_cooldown_s
            log.warning("provider %s failed (%s: %s); cooling down", p.name, type(e).__name__, e)
    raise RuntimeError("all LLM providers failed or are cooling down")


def embed(text_: str) -> list[float]:
    """Embeddings always come from the local Ollama (all-minilm, 384 dims, matches faq_chunks.embedding)."""
    client = OpenAI(base_url=settings.local_llm_url, api_key="ollama", timeout=settings.llm_timeout_s, max_retries=0)
    return client.embeddings.create(model=settings.embed_model, input=text_).data[0].embedding
