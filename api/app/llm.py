import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
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
    send_temperature: bool = True  # some hosted models reject temperature below their default
    strict: bool = False  # a 400 raises ProviderRejected instead of falling through


# Priority order. Keyless providers other than local/OVH are skipped. All are OpenAI-compatible.
# Open-weight models only; limits per github.com/mnfst/awesome-free-llm-apis.
PROVIDERS = [
    Provider("local", settings.local_llm_url, "ollama" if settings.local_llm_url else "", settings.local_llm_model),  # empty LOCAL_LLM_URL turns it off (hosted deploy)
    Provider("groq", "https://api.groq.com/openai/v1", settings.groq_api_key, "openai/gpt-oss-20b"),
    Provider("nvidia", "https://integrate.api.nvidia.com/v1", settings.nvidia_api_key, "openai/gpt-oss-20b"),
    Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", settings.gemini_api_key, "gemini-2.5-flash"),
    Provider("openrouter","https://openrouter.ai/api/v1", settings.openrouter_api_key,
             "google/gemma-4-31b-it:free"),
    Provider("ovh", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "anonymous", "gpt-oss-20b"),
    # Last and keyless unless ANTHROPIC_API_KEY is set; never first.
    Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, settings.anthropic_model,
             send_temperature=False, strict=True),
]


class ProviderRejected(RuntimeError):
    """A strict provider answered 400: surface it, never score it as a failed scenario or fall through."""


_pinned: ContextVar[list[Provider] | None] = ContextVar("llm_pinned", default=None)


@contextmanager
def pinned(providers: list[Provider]):
    """Make chat() calls without an explicit providers list use only these (scorecard runs)."""
    token = _pinned.set(providers)
    try:
        yield
    finally:
        _pinned.reset(token)


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, body) for prompts/<name>.md; first line is `version: <v>`."""
    head, _, body = (settings.prompts_dir / f"{name}.md").read_text().partition("\n")
    return head.removeprefix("version:").strip(), body.strip()


LLM_TEMPERATURE = 0


def _call(p: Provider, messages: list[dict]) -> dict:
    client = OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=settings.llm_timeout_s, max_retries=0)
    start = time.perf_counter()
    kw = {'temperature': LLM_TEMPERATURE} if p.send_temperature else {}
    resp = client.chat.completions.create(model=p.model, messages=messages, **kw)
    return {
        "content": resp.choices[0].message.content or "",
        "model": f"{p.name}:{p.model}",
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


def chat(messages: list[dict], providers: list[Provider] | None = None) -> dict:
    """Try providers in order; any API error (429, 5xx, timeout, auth) cools that provider down and moves on."""
    providers = providers if providers is not None else (_pinned.get() or PROVIDERS)
    now = time.monotonic()
    for p in providers:
        if not p.api_key or p.cooldown_until > now:
            continue
        try:
            return _call(p, messages)
        except BadRequestError as e:
            if p.strict:  # status code only: the body may echo the request
                raise ProviderRejected(f"{p.name} rejected the request: HTTP {e.status_code}") from e
            # this request's fault, not the provider's: try the next one, no cooldown
            log.warning("provider %s rejected the request: %s", p.name, e.status_code)
        except OpenAIError as e:
            p.cooldown_until = time.monotonic() + settings.provider_cooldown_s
            log.warning("provider %s failed (%s: %s); cooling down", p.name, type(e).__name__, e)
    raise RuntimeError("all LLM providers failed or are cooling down")


def embed(text_: str) -> list[float]:
    """Embeddings always come from the local Ollama (all-minilm, 384 dims, matches faq_chunks.embedding)."""
    client = OpenAI(base_url=settings.local_llm_url, api_key="ollama", timeout=settings.llm_timeout_s, max_retries=0)
    return client.embeddings.create(model=settings.embed_model, input=text_).data[0].embedding
