"""Unit tests for Authenticity Engine, Claim Extractor, Context Verifier, and Media Triage."""

import pytest
import numpy as np
from PIL import Image
from app.utils.authenticity_engine import LocalAITextDetector, LocalClaimExtractor
from app.utils.media_triage import MediaTriage


def test_ai_text_detector_human_vs_short():
    detector = LocalAITextDetector()
    
    # Short text
    short_res = detector.analyze("Hello world!")
    assert short_res["status"] == "insufficient_evidence"

    # Human-like conversational text
    human_text = "I went to the store today and found a cool retro game! Definitely bringing back memories from the 90s."
    human_res = detector.analyze(human_text)
    assert human_res["score"] < 0.60
    assert human_res["status"] in ("likely_human", "possibly_ai_generated")


def test_claim_extractor_casual_vs_assertion():
    extractor = LocalClaimExtractor()

    # Casual post / opinion / personal experience -> NO claims
    casual_text = "It is so much fun to take unstructured data in PDFs and turn them into interactive websites."
    assert extractor.extract(casual_text) == []

    advice_text = "Start with one feature: plan it, build it, review it."
    assert extractor.extract(advice_text) == []

    # Real factual event with assertion trigger and named entity
    claim_text = "Anthropic announced Claude Fable 5.1 today with new multimodal capabilities."
    claims = extractor.extract(claim_text)
    assert len(claims) == 1
    assert claims[0]["entity"] == "Anthropic"
    assert claims[0]["trigger"] == "announced"


def test_media_pixel_forensics():
    triage = MediaTriage()

    # Synthetic image: smooth flat interior with extreme edge transition (high kurtosis)
    synthetic_arr = np.zeros((200, 200, 3), dtype=np.uint8)
    synthetic_arr[50:150, 50:150] = 255
    # Smooth flat blocks
    synth_img = Image.fromarray(synthetic_arr)
    forensics = triage._analyze_pixel_forensics(synth_img)
    assert "kurtosis" in forensics
    assert "hf_peak_density" in forensics
    assert "flat_patch_var" in forensics
    assert forensics["flat_patch_var"] < 4.0


@pytest.mark.asyncio
async def test_media_context_correlation():
    triage = MediaTriage()
    # Check that AI generator keywords in post text properly boost AI score
    res = await triage.fetch_and_analyze_metadata(
        url="https://pbs.twimg.com/media/HRyFjkWbkAElc84.jpg",
        post_text="GPT-6 Astra Text-to-3D + Image-to-3D are now live on WaveSpeed"
    )
    assert res["is_ai_generated"] is True
    assert res["verdict"] == "LIKELY_AI_GENERATED"
    assert "text-to-3d" in res["details"].lower() or "kurtosis" in res["details"].lower()
