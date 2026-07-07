from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.demo1.coref_disambig import disambiguate_entities, resolve_coreferences
from backend.demo1.multilingual import analyze_multilingual, detect_language, SUPPORTED_LANGUAGES

router = APIRouter(tags=["NLP"])

class TextInput(BaseModel):
    text: str

@router.post("/disambiguate")
def disambiguate(body: TextInput):
    """Resolve ambiguous entity mentions to canonical real-world forms."""
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(400, "Text too short")
    return disambiguate_entities(body.text)

@router.post("/coreference")
def coreference(body: TextInput):
    """Resolve pronouns and noun phrases to their referent entities."""
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(400, "Text too short")
    return resolve_coreferences(body.text)

@router.get("/languages")
def languages():
    """List all supported languages."""
    return {"languages": SUPPORTED_LANGUAGES}

@router.post("/analyze/multilingual")
def analyze_multilingual_endpoint(
    body: TextInput,
    lang: str = Query("auto", description="Language code: en, zh, es, fr, de, ja, ar, pt, auto")
):
    """Analyze text in any supported language."""
    if not body.text or len(body.text.strip()) < 10:
        raise HTTPException(400, "Text too short")
    return analyze_multilingual(body.text, lang)

@router.get("/multilingual/languages")
def languages_alias():
    """Alias for the Vue frontend (/multilingual/languages)."""
    return {"languages": SUPPORTED_LANGUAGES}

@router.post("/multilingual/analyze")
def analyze_multilingual_alias(
    body: TextInput,
    lang: str = Query("auto", description="Language code: en, zh, es, fr, de, ja, ar, pt, auto")
):
    """Alias for the Vue frontend (/multilingual/analyze)."""
    if not body.text or len(body.text.strip()) < 10:
        raise HTTPException(400, "Text too short")
    return analyze_multilingual(body.text, lang)

@router.post("/detect/language")
def detect_language_endpoint(body: TextInput):
    """Detect the language of any text."""
    if not body.text or len(body.text.strip()) < 5:
        raise HTTPException(400, "Text too short")
    return detect_language(body.text)
