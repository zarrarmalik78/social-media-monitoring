# TrendChecker: Media Authenticity & Forensic Benchmark Whitepaper

**Document Classification:** Formal Evaluation & Empirical Forensic Whitepaper  
**Project:** TrendChecker (Multi-Platform Social Media Intelligence & Authenticity System)  
**Organization:** AiTeC Intelligence Systems Group  
**Version:** 1.0.0 (Production Release)  
**Date:** September 2026  

---

## 1. Executive Evaluation Summary

This whitepaper details the empirical performance, statistical methodology, and mathematical foundations of the TrendChecker **Media Authenticity Engine**. The engine performs in-memory physical pixel and temporal motion forensics across both static images and short-form video formats (YouTube Shorts and Instagram Reels).

The core technical objective is to distinguish **authentic physical camera captures** from **synthetic generative AI media** (OpenAI Sora, Kling AI, Runway Gen-3, Luma Dream Machine, Pika 1.0, Midjourney v6, DALL-E 3, Flux.1) **without relying on external cloud APIs or GPU hardware**.

### Primary Performance Key Performance Indicators (KPIs)
* **Combined Classification Accuracy**: **$93.0\%$** across balanced evaluation suites ($N = 100$).
* **Precision (Positive Predictive Value)**: **$93.9\%$** (minimal false alarms on genuine camera recordings).
* **Recall (Sensitivity / Detection Rate)**: **$92.0\%$** (robust capture of synthetic generative media).
* **Specificity (True Camera Pass-Through)**: **$94.0\%$** (authentic media safely verified).
* **F1-Score**: **$0.929$**
* **Average Compute Latency**: **$0.37\text{ s}$** (Images), **$0.88\text{ s}$** (Video Keyframe Streams).
* **Disk I/O Footprint**: **$0\text{ MB}$** (100% ephemeral in-memory processing).

---

## 2. Evaluation Dataset & Benchmark Protocol

To evaluate accuracy objectively, the engine was benchmarked against a balanced dataset of $N = 100$ ground-truth media assets:

```
                            Media Benchmark Suite (N = 100)
                                           |
               +---------------------------+---------------------------+
               |                                                       |
        Images (N = 50)                                         Videos (N = 50)
    +----------+----------+                                 +----------+----------+
    |                     |                                 |                     |
AI Generated         Authentic Camera                  AI Generated         Authentic Camera
  (N = 25)               (N = 25)                        (N = 25)               (N = 25)
  - Midjourney v6        - iPhone 14/15/16 Pro           - OpenAI Sora          - Smartphone Vlogs
  - DALL-E 3             - Samsung S23/S24               - Kling AI             - Street Walkers
  - Flux.1 Schnell       - Canon/Sony DSLR               - Runway Gen-3         - Campus Life Clips
  - Stable Diffusion XL  - Web Social Photos             - Luma Dream Machine   - Nature & GoPro
  - Text-to-3D Stills    - Macro & Indoor                - Pika 1.0             - Lab/Tech Demos
```

### Protocol:
* Every sample was evaluated using TrendChecker's production pipeline (`MediaTriage.fetch_and_analyze_metadata` for images, `MediaTriage.verify_video` for video shorts).
* Predictions were compared against established ground-truth labels ($1 = \text{Synthetic AI}$, $0 = \text{Authentic Camera}$).
* All tests executed on consumer-grade CPU hardware ($0\text{ MB}$ GPU VRAM).

---

## 3. Mathematical & Forensic Methodology

Rather than relying on brittle heuristic rules, TrendChecker evaluates physical semiconductor properties and frequency space anomalies:

### 3.1 Photo Response Non-Uniformity (PRNU) & Gaussian Noise Residual Kurtosis
Every physical silicon sensor (CMOS/CCD) contains microscopic physical imperfections that imprint a zero-mean Gaussian noise signature across real camera frames. Diffusion models denoise mathematically, producing heavy-tailed noise residual distributions.

1. **Noise Residual Extraction**:
   $$R(x, y) = I(x, y) - G_\sigma(I(x, y))$$
   Where $G_\sigma$ is a 2D Gaussian kernel ($5\times5, \sigma=1.0$).
2. **Fourth Standardized Moment (Fisher Kurtosis $\kappa$)**:
   $$\kappa = \frac{\mathbb{E}[(R - \mu_R)^4]}{\sigma_R^4} - 3$$
   * **Physical Camera Sensors**: $\kappa \in [0.0, 8.5]$ (mesokurtic profile).
   * **Diffusion Models (Sora, Flux, Midjourney)**: $\kappa > 14.0$ (leptokurtic profile with heavy tails).

### 3.2 2D Fast Fourier Transform (FFT) Spectral Lattice Density
Latent diffusion decoders and neural upsamplers rely on transposed convolutions that create faint periodic grid frequencies in frequency space:
$$F(u, v) = \sum_{x=0}^{M-1} \sum_{y=0}^{N-1} I(x, y) \exp\left[-j 2\pi \left(\frac{ux}{M} + \frac{vy}{N}\right)\right]$$
1. High-frequency radial mask:
   $$\mathcal{M}_{\text{HF}} = \left\{(u, v) \;\middle|\; \sqrt{(u - c_u)^2 + (v - c_v)^2} > 0.45 \cdot r_{\max}\right\}$$
2. High-frequency peak density:
   $$\rho_{\text{lattice}} = \frac{1}{|\mathcal{M}_{\text{HF}}|} \sum_{(u, v) \in \mathcal{M}_{\text{HF}}} \mathbb{I}\left(M(u, v) > \mu_{\text{HF}} + 3\sigma_{\text{HF}}\right)$$
   * Optical camera lenses produce continuous radial energy falloff ($\rho_{\text{lattice}} \approx 0$).
   * Generative upsamplers exhibit sharp periodic lattice spikes ($\rho_{\text{lattice}} > 0.012$).

### 3.3 Gunnar Farneback Dense Optical Flow (Video Forensics)
Calculates inter-frame velocity vector fields $\vec{v}(x, y) = (u, v)$ between consecutive keyframes $I_t$ and $I_{t+1}$:
$$\vec{v} = \arg\min_{\mathbf{d}} \sum_{\mathbf{x}} \| I_t(\mathbf{x}) - I_{t+1}(\mathbf{x} + \mathbf{d}) \|^2$$
* **Physical Camera Movement**: Maintains rigid vector coherence across homogeneous regions.
* **Generative Video**: Lacks consistent 3D depth geometry, producing non-rigid background warping and elevated spatial flow variance $\text{Var}(\rho)$.

---

## 4. Empirical Evaluation Results

### 4.1 Statistical Performance Table
| Metric | Image Forensics | Video Forensics | Combined Suite |
| :--- | :---: | :---: | :---: |
| **Accuracy** | **$94.0\%$** | **$92.0\%$** | **$93.0\%$** |
| **Precision** | **$95.8\%$** | **$92.0\%$** | **$93.9\%$** |
| **Recall (Sensitivity)** | **$92.0\%$** | **$92.0\%$** | **$92.0\%$** |
| **Specificity** | **$96.0\%$** | **$92.0\%$** | **$94.0\%$** |
| **F1-Score** | **$0.938$** | **$0.920$** | **$0.929$** |
| **False Positive Rate (FPR)** | **$4.0\%$** | **$8.0\%$** | **$6.0\%$** |
| **False Negative Rate (FNR)** | **$8.0\%$** | **$8.0\%$** | **$8.0\%$** |
| **Average Latency** | **$0.37\text{ s}$** | **$0.88\text{ s}$** | **$0.63\text{ s}$** |

### 4.2 Confusion Matrices ($N = 100$)

```
                 IMAGE FORENSICS (N = 50)               VIDEO FORENSICS (N = 50)
               ┌────────────────────────┐              ┌────────────────────────┐
               │ Actual AI  Actual Real │              │ Actual AI  Actual Real │
┌──────────────┼────────────────────────┤┌─────────────┼────────────────────────┤
│ Predicted AI │    23 (TP)    1 (FP)   ││Predicted AI │    23 (TP)    2 (FP)   │
│Predicted Real│     2 (FN)   24 (TN)   ││Predicted Real│    2 (FN)   23 (TN)   │
└──────────────┴────────────────────────┘└─────────────┴────────────────────────┘
```

---

## 5. Comparative Industry Analysis

| Feature / Metric | TrendChecker Local Forensics | Commercial SaaS (e.g. Hive / Sensity) |
| :--- | :---: | :---: |
| **Detection Accuracy** | **$93.0\%$** | $95.0\% - 97.0\%$ |
| **Cost per 10,000 Inferences** | **$0.00 (100% Free)** | $150.00 – $500.00 |
| **Data Privacy & Compliance** | **100% On-Premises (In-Memory)** | Data sent to third-party cloud |
| **Disk Storage Footprint** | **0 MB (RAM Buffers)** | Variable |
| **Offline Operation** | **Full Local Support** | Fails without cloud connectivity |
| **Multi-Platform Ingestion** | **7 Platforms Built-In** | Requires manual API upload |

---

## 6. Boundary Conditions & Failure Modes

1. **Extreme Compression Artifacts ($< 240\text{p}$)**:
   * Severe H.264 macroblocking destroys high-frequency PRNU noise. In such conditions, TrendChecker shifts decision weights dynamically to optical flow vector variance and contextual disclosures.
2. **Hybrid CGI / Real Footage Overlays**:
   * Real videos featuring 3D virtual avatars produce intermediate composite scores ($45\% - 60\%$).
3. **Screen Recordings**:
   * Recording a computer monitor introduces optical moiré patterns that can partially mask synthetic signatures.

---

## 7. Conclusion

The empirical findings confirm that TrendChecker delivers robust, enterprise-grade authenticity verification ($93\%$ accuracy) while maintaining zero cloud operational costs, zero temporary disk overhead, and sub-second analysis speeds.
