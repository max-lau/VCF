from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.demo1.summary_scorer import score_summary
import json

router = APIRouter(tags=["Summary"])

class TextInput(BaseModel):
    text: str

@router.post("/summary/score")
def summary_score(body: TextInput):
    """Score a summary against its source document."""
    try:
        data    = json.loads(body.text)
        source  = data.get("source", "")
        summary = data.get("summary", "")
        if not source or not summary:
            raise HTTPException(400, "Provide JSON with 'source' and 'summary' fields")
        return score_summary(source, summary)
    except json.JSONDecodeError:
        raise HTTPException(400, "Body must be JSON: {source: '...', summary: '...'}")
