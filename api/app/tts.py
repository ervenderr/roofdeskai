"""Natural-sounding speech for the demo's Talk button (Gemini text-to-speech). The browser voice is the fallback."""
import base64
import io
import logging
import wave

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config import settings
from .ratelimit import allow

log = logging.getLogger("leadpilot.tts")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SAMPLE_RATE = 24000  # Gemini returns 16-bit mono PCM at 24 kHz
PER_MINUTE = 20  # every call costs quota, so keep this tighter than /chat

router = APIRouter()


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)


def speak_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not allow(f"speak:{ip}", PER_MINUTE):
        raise HTTPException(429, "Too many requests, please slow down.")


def synthesize(text: str) -> bytes:
    """WAV bytes for `text`. Raises httpx.HTTPError or KeyError/ValueError on a bad provider response."""
    r = httpx.post(URL.format(model=settings.tts_model), headers={"x-goog-api-key": settings.gemini_api_key},
                   json={"contents": [{"parts": [{"text": text}]}],
                         "generationConfig": {"responseModalities": ["AUDIO"],
                                              "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": settings.tts_voice}}}}},
                   timeout=settings.llm_timeout_s)
    r.raise_for_status()
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


@router.post("/speak", dependencies=[Depends(speak_rate_limit)])
def speak(body: SpeakIn):
    if not settings.gemini_api_key:
        raise HTTPException(503, "Voice is not configured.")
    try:
        return Response(synthesize(body.text), media_type="audio/wav")
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        log.exception("text-to-speech failed")
        raise HTTPException(502, "Voice is unavailable right now.")
