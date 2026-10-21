import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .admin import router as admin_router
from .agent import conversation_token, handle_turn, token_matches
from .config import settings
from .db import engine
from .faq import seed_faq
from .ratelimit import chat_rate_limit

log = logging.getLogger("leadpilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        seed_faq()
    except Exception:
        pass  # already logged; the API still serves, FAQ lookups just return nothing
    yield


app = FastAPI(title="LeadPilot", lifespan=lifespan)
app.include_router(admin_router)


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
