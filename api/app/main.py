import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text

from .admin import router as admin_router
from .bootstrap import bootstrap_schema
from .outreach_routes import router as outreach_router
from .pilot import router as pilot_router
from .agent import conversation_token, handle_turn, token_matches
from .config import settings
from .db import engine
from .faq import seed_faq
from .ratelimit import chat_rate_limit

log = logging.getLogger("leadpilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_schema()  # a failure here should stop the start: nothing works without a schema
    try:
        seed_faq()
    except Exception:
        pass  # already logged; the API still serves, FAQ lookups just return nothing
    yield


app = FastAPI(title="RoofDesk AI", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(outreach_router)
app.include_router(pilot_router)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["POST"], allow_headers=["content-type"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    conversation_id: int | None = None
    conversation_token: str | None = None  # returned when a conversation starts; required to continue it


class ChatOut(BaseModel):
    conversation_id: int
    conversation_token: str
    reply: str


@app.get("/health")
def health():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"ok": True}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(chat_rate_limit)])
def chat(body: ChatIn):
    if body.conversation_id is not None and not token_matches(body.conversation_id, body.conversation_token):
        raise HTTPException(404, "conversation not found")
    try:
        cid, reply = handle_turn(body.message, body.conversation_id)
    except LookupError:
        raise HTTPException(404, "conversation not found")
    except RuntimeError:
        log.exception("all LLM providers failed (conversation %s)", body.conversation_id)
        raise HTTPException(502, "The assistant is unavailable right now.")
    return ChatOut(conversation_id=cid, conversation_token=conversation_token(cid), reply=reply)


# The demo page is served by the API itself so one tunnel carries the page, chat and form. Mounted last: API routes win.
if settings.site_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.site_dir, html=True), name="site")
