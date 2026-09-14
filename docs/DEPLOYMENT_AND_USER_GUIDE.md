# TrendChecker: Deployment, Setup & Operational User Manual

**Document Classification:** Operations, Deployment & User Handbook  
**Project:** TrendChecker (Multi-Platform Social Media Intelligence & Authenticity System)  
**Version:** 1.0.0 (Production Release)  
**Target Audience:** System Evaluators, Systems Administrators, Research Faculty, Deployment Engineers  

---

## 1. System Requirements & Prerequisites

TrendChecker is engineered for lightweight, cross-platform operation without requiring dedicated GPU acceleration or third-party cloud AI tokens.

### 1.1 Minimum & Recommended Hardware Specifications
| Hardware Component | Minimum Requirement | Recommended Specification |
| :--- | :--- | :--- |
| **Processor (CPU)** | 64-bit Dual-Core ($2.0\text{ GHz}$) | 64-bit Quad-Core (Intel i5/i7, AMD Ryzen, Apple M-Series) |
| **System Memory (RAM)** | $4\text{ GB}$ Available RAM | $8\text{ GB} - 16\text{ GB}$ High-Speed RAM |
| **Disk Storage** | $250\text{ MB}$ free disk space | $1\text{ GB}$ (allowing for persistent SQLite historical logs) |
| **Network Interface** | Standard Broadband Connection | High-Speed Low-Latency Internet |
| **Graphics (GPU)** | **None required (GPU-Free)** | Integrated or Discrete (CPU vector acceleration) |

### 1.2 Supported Operating Systems
* **Microsoft Windows**: Windows 10, Windows 11, Windows Server 2019/2022 (x86_64).
* **Linux**: Ubuntu 20.04+, Debian 11+, RHEL/CentOS 8+, Arch Linux (x86_64 / aarch64).
* **Apple macOS**: macOS Monterey (12.0)+, macOS Ventura, macOS Sonoma, macOS Sequoia (Intel & Apple Silicon M1-M4).

### 1.3 Python Runtime Environment
* **Supported Versions**: Python 3.10, 3.11, 3.12, 3.13.
* **Verified Runtime**: Python 3.13.5 (64-bit).

---

## 2. Step-by-Step Installation & Setup

Follow these steps to set up and verify the TrendChecker environment from scratch:

### Step 1: Open Terminal / PowerShell in Project Root
Navigate to the root directory containing `run_web.py` and `requirements.txt`:
```powershell
cd "d:\AiTeC Internship '26\TrendChecker - SSM\social-media-monitoring"
```

### Step 2: Create a Clean Python Virtual Environment (Recommended)
Isolating dependencies ensures no conflicts with system-level packages:
```bash
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS Bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Production Dependencies
Install all required web, forensic, and scraping libraries:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Verify Installation with Automated Test Suite
Execute the built-in test suite to verify that all collectors, models, and forensic engines are functioning properly:
```bash
python -m pytest tests/ -v
```
**Expected Result**: `38 passed in ~10s` ($100\%$ pass rate).

---

## 3. System Execution & Interfaces

TrendChecker provides two independent runtime interfaces: an interactive **Cyber-Glass Web Dashboard** and a scriptable **Terminal Command-Line Interface (CLI)**.

### Mode A: Web Dashboard (Primary Interface)
Start the high-performance asynchronous FastAPI web server:
```bash
python run_web.py
```
* **Host Address**: `127.0.0.1` (Localhost)
* **Port**: `8000`
* **Access URL**: Open **`http://127.0.0.1:8000`** in Google Chrome, Microsoft Edge, Mozilla Firefox, or Safari.

### Mode B: Terminal Command-Line Interface (CLI)
For headless server environments or automated batch jobs:
```bash
python run_cli.py
```
* Interactive CLI allows querying specific platforms, setting post retrieval limits, inspecting JSON structures, and generating tabular reports in the terminal.

---

## 4. Web Dashboard User Manual

The web dashboard features a modern **Cyber-Glass UI** designed for high-density intelligence monitoring:

```
+-----------------------------------------------------------------------------------+
|  [⚡ 7-SOURCES] TrendChecker        (● System Active)       [⚙️ Scraper Settings] |
+-----------------------------------------------------------------------------------+
|  [ 🔍 Search keywords (e.g. OpenAI, NUST, Admissions)... ] [⚡ All Sources] [Run] |
+-----------------------------------------------------------------------------------+
|  [📊 Sentiment Analytics] [📈 Topic Breakdown] [❤️ Likes] [💬 Comments] [🔄 Shares] |
+-----------------------------------------------------------------------------------+
|  [All Feeds] [X] [Facebook] [Reddit] [YouTube] [Instagram] [LinkedIn] [News]     |
|                                                                                   |
|  POST CARD:                                                                       |
|  Author: @OpenAI • Platform: YouTube • Sentiment: Positive                        |
|  Text: "OpenAI Sora AI Video Demo: Tokyo Walk in Snow #shorts #sora"              |
|  [ Video Player Preview with Play Badge ]                                         |
|  [ 🎬 Verify Video ]  -->  [ 🤖 LIKELY AI VIDEO (SORA) (98%) ] [ Verified ✓ ]     |
|  [ ✍️ Text: Human (80%) ] [ ℹ️ Fact-Check: SUPPORTED ] [ Citations: 4 Sources ]   |
+-----------------------------------------------------------------------------------+
```

### 4.1 Running Multi-Platform Searches
1. **Search Input**: Enter search terms (e.g., `OpenAI`, `NUST`, `Admissions 2026`) in the top search bar.
2. **Platform Selector**: Choose `⚡ All 7 Sources (Parallel)` or select a single platform.
3. **Retrieval Limit**: Select between $10$, $20$, $50$, or $100$ items per query.
4. **Execute**: Click **`Run Scan`** or press `Enter`. The system queries all selected collectors concurrently and displays normalized results chronologically.

### 4.2 Using the Advanced Boolean Query Builder
Click the query syntax chips or open the builder modal:
* `AND` / `OR` Boolean grouping.
* Exact match phrases (`"artificial intelligence"`).
* Account filters (`from:OpenAI`).
* Media filters (`filter:media`, `filter:links`).
* Threshold filters (`min_faves:100`, `min_retweets:20`).

### 4.3 Authenticity & Fact-Checking Triage
Every post card displays an integrated authenticity bar:
* **Text Analysis Badge**: Displays whether the written content was synthesized by an LLM (`Text: Human (80%)` vs `Text: AI-Gen (85%)`).
* **Fact-Check Status**:
  * **`SUPPORTED`** (Green): Indicates the claim is corroborated by independent international news outlets. Click **`Extracted Claims & News Citations`** to inspect the cited articles.
  * **`UNVERIFIED`** (Yellow): Factual assertion made, but no independent news outlet has confirmed it.
  * **`NO CLAIMS`** (Grey): Casual opinion or personal commentary that contains no empirical claims.

### 4.4 On-Demand Image Forensics
For posts containing photos or images:
1. Locate the image card in the feed.
2. Click **`[ ✨ Verify Image ]`**.
3. In $<3$ seconds, the system computes the 2D FFT spectral peak density and Gaussian noise kurtosis directly in RAM, updating the badge to:
   * 🟣 **`LIKELY AI GENERATED`** (with detailed kurtosis values and lattice frequencies).
   * 🟢 **`AUTHENTIC CAMERA PHOTO`** (confirming natural sensor PRNU noise).

### 4.5 On-Demand Video Forensics (YouTube Shorts & Instagram Reels)
For posts containing video, Shorts, or Reels:
1. Click the **`YouTube`** or **`Instagram`** platform pill tab.
2. Locate the video card with the embedded thumbnail and play overlay.
3. Click **`[ 🎬 Verify Video ]`**.
4. The system concurrently samples 4 keyframes in RAM and applies Gunnar Farneback dense optical flow tracking and PRNU noise kurtosis, updating the badge to:
   * 🟣 **`LIKELY AI VIDEO (SORA / KLING)`** (detecting non-rigid warping and synthetic kurtosis).
   * 🟢 **`NATURAL CAMERA VIDEO`** (confirming rigid real-world motion and physical sensor profiles).

---

## 5. Platform Account & Session Management

For platforms requiring authenticated sessions (e.g., protected X/Twitter feeds or Facebook groups):

1. Click **`⚙️ Scraper Settings`** in the top navigation bar.
2. Select the platform (`X`, `Facebook`).
3. Paste session cookies in JSON or Netscape format.
4. Click **`Save & Register Account`**. TrendChecker encrypts and stores the cookies in the local database for seamless rotation.
5. If rate-limits are encountered, click **`Reset Rate Limit Locks`** to cycle accounts immediately.

---

## 6. Troubleshooting & Operational FAQs

### Q: Port 8000 is already in use by another service.
**Resolution**: You can start the server on an alternative port by passing the `--port` flag:
```bash
python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8080
```
Then access `http://127.0.0.1:8080`.

### Q: `ModuleNotFoundError: No module named 'cv2'` or `numpy`.
**Resolution**: Ensure you are using the virtual environment where dependencies were installed:
```bash
pip install opencv-python numpy scipy pillow
```

### Q: Optical flow calculation returns `NATURAL CAMERA VIDEO` on an AI video.
**Resolution**: Ensure the video is not a heavily re-compressed screen capture. Highly compressed media ($<240\text{p}$) blurs high-frequency noise. The system relies more on contextual hashtags (`#sora`, `#kling`) in low-resolution conditions.

---

## 7. Operational Health Checklist

Before submitting or presenting:
- [x] Run `python -m pytest tests/` $\rightarrow$ Confirm 38/38 passing tests.
- [x] Launch `python run_web.py` $\rightarrow$ Confirm server starts on `http://127.0.0.1:8000`.
- [x] Run a test query (e.g., `OpenAI`) $\rightarrow$ Confirm multi-platform results load.
- [x] Verify an AI Short and a Camera Short $\rightarrow$ Confirm purple and green verification badges appear.
