"""
backend/demo1/medical_bert.py
============================
Local BioClinicalBERT integration for VCF medical text analysis.

BioClinicalBERT (emilyalsentzer/Bio_ClinicalBERT) is a masked language model
pre-trained on MIMIC-III clinical notes. The base model does not perform NER
out-of-the-box, so this module uses it for semantic similarity:

- Embed chunks of input medical text.
- Embed a curated list of WTC/VCF-relevant conditions.
- Return the best-matching conditions with confidence scores.

This runs entirely offline once the model is downloaded.
"""

import logging
import os
import re
from typing import List, Dict

import torch
import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MEDICAL_BERT_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
MAX_SEQ_LEN = 128
WTC_CONDITIONS = [
    "lung cancer",
    "non-small cell lung cancer",
    "adenocarcinoma of the lung",
    "mesothelioma",
    "thyroid cancer",
    "papillary thyroid carcinoma",
    "prostate cancer",
    "breast cancer",
    "colorectal cancer",
    "bladder cancer",
    "kidney cancer",
    "leukemia",
    "lymphoma",
    "multiple myeloma",
    "chronic obstructive pulmonary disease",
    "COPD",
    "asthma",
    "interstitial lung disease",
    "pulmonary fibrosis",
    "gastroesophageal reflux disease",
    "GERD",
    "sleep apnea",
    "chronic rhinosinusitis",
    "chronic laryngitis",
    "gastroesophageal reflux",
    "obstructive airway disease",
    "reactive airways dysfunction syndrome",
    "WTC-related condition",
    "World Trade Center-related condition",
    "9/11-related illness",
]

_tokenizer = None
_model = None
_device = None


def _load_model():
    """Lazy-load tokenizer and model."""
    global _tokenizer, _model, _device
    if _model is not None:
        return _tokenizer, _model, _device

    try:
        from transformers import AutoTokenizer, AutoModel
    except ImportError as e:
        raise RuntimeError("transformers not installed") from e

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"[MedicalBERT] Loading {MODEL_NAME} on {_device}...")
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    _model = AutoModel.from_pretrained(MODEL_NAME).to(_device)
    _model.eval()
    logger.info("[MedicalBERT] Model loaded")
    return _tokenizer, _model, _device


def _mean_pooling(model_output, attention_mask):
    """Mean-pool token embeddings using the attention mask."""
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).float()
    sum_embeddings = (token_embeddings * input_mask_expanded).sum(dim=1)
    return sum_embeddings / input_mask_expanded.sum(dim=1).clamp(min=1e-9)


def _embed(texts: List[str]) -> np.ndarray:
    tokenizer, model, device = _load_model()
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_SEQ_LEN,
        return_tensors="pt",
    )
    encoded = {k: v.to(device) for k, v in encoded.items()}
    with torch.no_grad():
        outputs = model(**encoded)
    embeddings = _mean_pooling(outputs, encoded["attention_mask"])
    return embeddings.cpu().numpy()


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / norms.clip(min=1e-9)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentence-ish chunks."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def extract_medical_conditions(text: str, top_k: int = 8, threshold: float = 0.45) -> List[Dict]:
    """
    Use BioClinicalBERT embeddings to find WTC-relevant conditions in text.
    Returns a list of condition matches with confidence scores.
    """
    if not text or len(text.strip()) < 20:
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    try:
        text_embeddings = _normalize(_embed(sentences))
        condition_embeddings = _normalize(_embed(WTC_CONDITIONS))

        # cosine similarity matrix: sentences x conditions
        similarities = text_embeddings @ condition_embeddings.T

        matches = []
        seen = set()
        for sent_idx, cond_scores in enumerate(similarities):
            for cond_idx, score in enumerate(cond_scores):
                if score >= threshold:
                    condition = WTC_CONDITIONS[cond_idx]
                    if condition in seen:
                        continue
                    seen.add(condition)
                    matches.append({
                        "name": condition,
                        "relevance": round(float(score), 3),
                        "wtc_related": True,
                        "certified": False,
                        "actionable": True,
                        "note": f"Mentioned in context: {sentences[sent_idx][:120]}",
                        "source": "bioclinicalbert",
                    })

        matches.sort(key=lambda x: x["relevance"], reverse=True)
        return matches[:top_k]
    except Exception as e:
        logger.warning(f"[MedicalBERT] extraction failed: {e}")
        return []


def is_available() -> bool:
    try:
        _load_model()
        return True
    except Exception as e:
        logger.warning(f"[MedicalBERT] not available: {e}")
        return False
