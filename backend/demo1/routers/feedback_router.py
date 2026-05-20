from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.demo1.database import (
    save_feedback, get_feedback_queue, mark_reviewed, get_retraining_data
)

router = APIRouter(tags=["Feedback"])

class FeedbackInput(BaseModel):
    analysis_id:     int
    text:            str
    predicted:       str
    predicted_score: float
    corrected:       Optional[str] = None
    feedback_type:   str = "sentiment_correction"
    notes:           Optional[str] = ""

class ReviewInput(BaseModel):
    feedback_id: int

@router.post("/feedback")
def submit_feedback(body: FeedbackInput):
    row_id = save_feedback(
        analysis_id     = body.analysis_id,
        text            = body.text,
        predicted       = body.predicted,
        predicted_score = body.predicted_score,
        corrected       = body.corrected,
        feedback_type   = body.feedback_type,
        notes           = body.notes
    )
    return {
        "feedback_id": row_id,
        "message": "Feedback saved — added to retraining queue",
        "retraining_trigger": "Queue this sample for next model update"
    }

@router.get("/feedback/queue")
def feedback_queue():
    items = get_feedback_queue(reviewed=False)
    return {"pending": len(items), "items": items}

@router.post("/feedback/review")
def review_feedback(body: ReviewInput):
    mark_reviewed(body.feedback_id)
    return {"message": f"Feedback {body.feedback_id} marked as reviewed"}

@router.get("/feedback/retraining-data")
def retraining_data():
    samples = get_retraining_data()
    return {
        "total_samples": len(samples),
        "message": f"{len(samples)} corrected samples ready for retraining",
        "samples": samples
    }
