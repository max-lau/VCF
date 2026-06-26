from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import anthropic
import os

router = APIRouter(prefix="/chat", tags=["Chat"])

SYSTEM_PROMPT = """You are ParaIQ Assistant — a helpful AI built into the ParaIQ legal practice management platform.

You help law firm staff (lawyers, paralegals, legal assistants) use ParaIQ effectively.

You can help with:
- Navigating any feature in ParaIQ (dashboard, matters, documents, discovery, depositions, motions, contracts, privilege log, exports, AI analysis tools)
- Understanding AI analysis results — what entity pills mean, how the sentiment bar works, how to read clause lists
- Uploading documents and running analysis
- Privilege log classifications and workflow
- Batch analysis, multilingual analysis, and NLP tools
- Exporting PDF bundles, DOCX reports, and CSV privilege logs
- User roles and what each role can access

Guidelines:
- Be concise and practical — users are busy legal professionals
- Give numbered step-by-step instructions when explaining how to do something
- If asked for actual legal advice (not app usage), politely clarify you can only help with using ParaIQ
- If you cannot resolve the issue after 2 attempts, suggest the user contact human support
- Keep responses under 180 words unless a detailed walkthrough is genuinely needed
- Never make up features that don't exist in ParaIQ"""

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class ChatMsg(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMsg] = []

class ChatResponse(BaseModel):
    reply: str
    suggest_escalation: bool = False

ESCALATION_SIGNALS = [
    "cannot help", "can't help", "not able to help",
    "contact support", "human support", "speak to someone",
    "reach out to", "please contact",
]

@router.post("/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest):
    try:
        messages = [{"role": m.role, "content": m.content} for m in req.history[-10:]]
        messages.append({"role": "user", "content": req.message})

        resp = _client.messages.create(
            model=os.getenv("CHAT_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=350,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = resp.content[0].text.strip()
        escalate = any(sig in reply.lower() for sig in ESCALATION_SIGNALS)
        return ChatResponse(reply=reply, suggest_escalation=escalate)

    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[chat_router] Error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
