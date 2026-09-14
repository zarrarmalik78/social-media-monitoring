# TrendChecker: AI Models & Algorithms Details

This document provides a detailed, technical breakdown of the specific models and algorithms used in each stage of the **TrendChecker AI Processing Pipeline**. You can use this information to add more technical depth to your Nano Banana diagram, or include it as a cheat sheet for your presentation to your supervisor.

## 1. Text Analysis Pipeline
**Objective:** Detect if a social media post's text is AI-generated (e.g., by ChatGPT).
- **Core Algorithm:** Lexical Shannon Entropy Analysis.
- **How it Works:** 
  - AI language models tend to choose highly probable words, resulting in very predictable text with low "entropy" (randomness).
  - Human writing is more chaotic, uses diverse vocabulary, and has higher entropy.
  - The system calculates the probability distribution of words and assigns an entropy score. If the score falls below a certain threshold, the text is flagged as `LIKELY_AI_GENERATED`.

## 2. Claim Fact-Checking Pipeline
**Objective:** Verify the factual accuracy of claims made in the text.
- **Core Algorithm:** Domain Exclusion and Multi-Source Consensus.
- **How it Works:**
  - Extracts key entities and claims from the text using basic NLP.
  - Searches the web for these claims but *strictly excludes* the original domain (e.g., if the claim is on Reddit, Reddit is ignored in the search).
  - Cross-references the claim against high-trust, independent domains (e.g., Reuters, AP News).
  - Requires a consensus of 3 to 5 independent sources to mark a claim as `SUPPORTED`.

## 3. Image Forensics Pipeline
**Objective:** Determine if an image is a real camera photo or AI-generated (e.g., Midjourney, DALL-E).
- **Core Algorithms:** 2D Fast Fourier Transform (FFT) and PRNU (Photo Response Non-Uniformity) Noise Kurtosis.
- **How it Works:**
  - **PRNU Noise:** Real cameras leave a unique, invisible hardware noise pattern (sensor imperfections) on every photo. AI generators create unnaturally smooth images without this hardware noise.
  - **2D FFT:** The system transforms the image pixels into the frequency domain. It analyzes the "Kurtosis" (sharpness of peaks in the frequency).
  - High Kurtosis (spiky frequencies) = AI generated artifact patterns.
  - Low Kurtosis (random noise) = Natural camera sensor noise.

## 4. Video Forensics Pipeline
**Objective:** Analyze video frames to detect AI-generated motion or deepfakes.
- **Core Algorithm:** Gunnar Farneback Optical Flow.
- **How it Works:**
  - Extracts keyframes directly in RAM (for speed and efficiency).
  - **Optical Flow:** Calculates the motion vectors of pixels between consecutive frames.
  - Natural video has consistent, physically possible motion blur and optical flow.
  - AI-generated videos (like Sora or Runway) often have temporal inconsistencies—pixels "morph" or teleport unnaturally between frames instead of moving physically. The algorithm detects these impossible motion vectors.

## 5. Authenticity Engine (Multi-Signal Scoring)
**Objective:** Combine all individual analyses into one final verdict.
- **Core Algorithm:** Composite Weighted Scoring Logic.
- **How it Works:**
  - Gathers the binary or continuous outputs from the Text, Claim, Image, and Video pipelines.
  - Applies a weighted formula to calculate an overall `confidence_score` (0% to 100%).
  - Determines a final system status (e.g., `VERIFIED_AUTHENTIC`, `AI_MANIPULATED`, or `UNVERIFIABLE`).
  - *Crucial Feature:* It operates 100% locally on the CPU without requiring heavy GPUs or external API calls, making it highly efficient.
