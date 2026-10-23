"""Speech to text for the demo's Talk button: the browser records, Gemini transcribes. Works in any browser that can record."""
import base64
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .config import settings
from .ratelimit import allow

log = logging.getLogger("leadpilot.stt")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_BYTES = 1_500_000  # about a minute of browser audio; the page stops recording well before that
PER_MINUTE = 20  # each call costs quota
ALLOWED = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg"}
PROMPT = ("Transcribe this audio exactly as spoken, in English. Reply with only the words, nothing else. "
          "If there is no speech, reply with exactly NONE.")

router = APIRouter()


def transcribe_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not allow(f"transcribe:{ip}", PER_MINUTE):
        raise HTTPException(429, "Too many requests, please slow down.")


def transcribe(data: bytes, mime: str) -> str:
    """The spoken words, or '' for silence. Raises httpx.HTTPError or KeyError/IndexError on a bad provider response."""
    r = httpx.post(URL.format(model=settings.stt_model), headers={"x-goog-api-key": settings.gemini_api_key},
                   json={"contents": [{"parts": [{"text": PROMPT},
                                                 {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}]}]},
                   timeout=settings.llm_timeout_s)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    return "" if text.upper().rstrip(".") == "NONE" else text


@router.post("/transcribe", dependencies=[Depends(transcribe_rate_limit)])
async def transcribe_audio(request: Request):
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime not in ALLOWED:
        raise HTTPException(415, "Send audio.")
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(413, "Recording too long.")
    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty recording.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Recording too long.")
    if not settings.gemini_api_key:
        raise HTTPException(503, "Voice is not configured.")
    try:
        return {"text": await run_in_threadpool(transcribe, data, mime)}
    except (httpx.HTTPError, KeyError, IndexError):
        log.exception("speech-to-text failed")
        raise HTTPException(502, "Voice is unavailable right now.")
