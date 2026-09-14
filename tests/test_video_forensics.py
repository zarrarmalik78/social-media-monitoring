"""Unit tests for Video Forensics, Optical Flow Motion Analysis, and Video Metadata Extraction."""

import pytest
import numpy as np
from app.utils.media_triage import MediaTriage


def test_extract_video_info_youtube_short():
    triage = MediaTriage()
    post = {
        "id": "yt_E_zSH6ydjIs",
        "url": "https://www.youtube.com/shorts/E_zSH6ydjIs",
        "platform": "youtube",
        "text": "OpenAI Sora AI Video Demo: Photorealistic Tokyo Walk #shorts #sora"
    }
    v_info = triage.extract_video_info(post, platform="youtube")
    assert v_info is not None
    assert v_info["is_video"] is True
    assert v_info["video_type"] == "youtube_short"
    assert v_info["video_id"] == "E_zSH6ydjIs"
    assert len(v_info["keyframes"]) == 4
    assert "https://img.youtube.com/vi/E_zSH6ydjIs/0.jpg" in v_info["keyframes"]


def test_extract_video_info_instagram_reel():
    triage = MediaTriage()
    post = {
        "id": "ig_reel_123",
        "url": "https://www.instagram.com/reel/C7q8s91A_test/",
        "platform": "instagram",
        "text": "Real-world test #reels #viral",
        "raw_data": {"code": "C7q8s91A_test", "is_video": True}
    }
    v_info = triage.extract_video_info(post, platform="instagram")
    assert v_info is not None
    assert v_info["is_video"] is True
    assert v_info["video_type"] == "instagram_reel"
    assert v_info["video_id"] == "C7q8s91A_test"


def test_analyze_video_motion_and_kurtosis():
    triage = MediaTriage()

    # Create 4 synthetic test keyframes simulating an AI video with extreme noise
    np.random.seed(42)
    ai_keyframes = []
    for i in range(4):
        noise = np.random.laplace(128, 24, (240, 360, 3))
        frame = np.clip(noise, 0, 255).astype(np.uint8)
        ai_keyframes.append(frame)

    ai_analysis = triage._analyze_video_temporal_and_spatial(
        keyframes=ai_keyframes,
        post_text="OpenAI Sora AI video generation text to video demo #sora #aivideo",
        video_title="OpenAI Sora Short"
    )
    assert ai_analysis["is_ai_video"] is True
    assert ai_analysis["verdict"] == "LIKELY_AI_VIDEO"
    assert ai_analysis["score"] >= 0.50

    # Create 4 camera-like test keyframes simulating smooth camera pan with Gaussian noise
    real_keyframes = []
    for i in range(4):
        sensor_noise = np.random.normal(128, 10, (240, 360, 3))
        frame = np.clip(sensor_noise, 0, 255).astype(np.uint8)
        real_keyframes.append(frame)

    real_analysis = triage._analyze_video_temporal_and_spatial(
        keyframes=real_keyframes,
        post_text="Walking across campus with my phone camera #vlog #walk",
        video_title="Campus Vlog"
    )
    assert real_analysis["is_ai_video"] is False
    assert real_analysis["verdict"] == "NATURAL_CAMERA_VIDEO"
    assert real_analysis["score"] < 0.50
