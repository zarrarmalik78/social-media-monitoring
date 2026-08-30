# Social Media Monitoring - Core X (Twitter) Search Prototype

A lightweight, local-first Python application for monitoring public X (Twitter) keywords and academic/institutional discussions (e.g. `IIUI`, `COMSATS`, `NUST`).

Built with a clean decoupled architecture:
$$\text{Keyword} \longrightarrow \text{X Collector (twscrape)} \longrightarrow \text{Normalized Post Model} \longrightarrow \text{Local SQLite Storage \& Display (CLI / Web UI)}$$

---

## 🚀 Key Features
- **Local-First & Lightweight**: Runs 100% locally on your machine with zero external cloud dependencies or Docker containers.
- **Normalized Schema**: Unified [`NormalizedPost`](file:///e:/AiTEC%20Internship%20'26/Social%20Media%20Monitoring/app/models/post.py) structure with fields for Post text, Author handle (`@username`), Display name, Date/Time, Permalink URL, Likes, Replies, Reposts, and Views.
- **Resilient X Collector**: Powered by `twscrape`, supporting session pooling, rate-limit rotation, and clean error handling (no unhandled crashes).
- **SQLite Persistence**: Local SQLite database storing search history and retrieved posts with automatic deduplication.
- **Interactive Dual Interfaces**:
  - **Terminal CLI**: Formatted colored cards and tables via `rich`.
  - **Local Web Dashboard**: Modern responsive UI with presets, live metrics, JSON export, and cookie manager.

---

## 📁 Project Structure

```
Social Media Monitoring/
├── app/
│   ├── collectors/
│   │   ├── base.py           # Abstract BaseCollector & custom error hierarchy
│   │   └── x_collector.py    # XCollector wrapping twscrape with account pooling
│   ├── models/
│   │   └── post.py           # NormalizedPost data model & twscrape parser
│   ├── database/
│   │   └── db.py             # SQLite persistence (posts & search history)
│   ├── web/
│   │   ├── app.py            # FastAPI local web backend
│   │   └── static/           # HTML5/CSS3/Vanilla JS dashboard
│   └── cli.py                # Rich terminal user interface
├── tests/
│   ├── test_models.py        # Schema & parsing tests
│   ├── test_db.py            # SQLite storage & filtering tests
│   └── test_collector.py     # Collector mock & exception handling tests
├── data/                     # Local SQLite databases (accounts.db, monitoring.db)
├── run_cli.py                # Entry point for Terminal CLI
├── run_web.py                # Entry point for Local Web App
├── requirements.txt          # Minimal Python dependencies
└── README.md                 # Documentation & Quickstart
```

---

## ⚙️ Installation

1. **Clone / Open the repository** in your terminal.
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔑 How X Authentication Works (Cookie Setup)

In modern X (2026), search timeline endpoints require an authenticated session. To avoid automated CAPTCHA or 2FA login challenges, the safest and easiest way to authenticate locally is by providing **browser session cookies** (`auth_token` and `ct0`) from any logged-in browser session on `x.com`.

### Steps to Extract Cookies:
1. Open [x.com](https://x.com) in your browser and ensure you are logged into an account.
2. Open Developer Tools: Press <kbd>F12</kbd> (or right-click anywhere and choose **Inspect**).
3. Navigate to **Application** (or **Storage** in Firefox) → **Cookies** → `https://x.com`.
4. Copy the values of:
   - `auth_token`
   - `ct0`

### Adding Cookies to the Account Pool:
You can register cookies via either the **CLI** or the **Web UI**:

- **Via CLI**:
  ```bash
  python run_cli.py add-cookie my_account "auth_token=YOUR_AUTH_TOKEN; ct0=YOUR_CT0"
  ```
- **Via Web Dashboard**:
  Click **"Manage Accounts"** or **"Add Cookies"** in the web interface header and paste the cookie string.

---

## 💻 Running the Application

### 1. Terminal CLI Interface
Run a search directly:
```bash
python run_cli.py search IIUI
python run_cli.py search COMSATS --limit 30
python run_cli.py search "\"International Islamic University\""
```

Interactive prompt mode:
```bash
python run_cli.py interactive
```

Check account pool readiness:
```bash
python run_cli.py status
```

View past searches & stored posts:
```bash
python run_cli.py history
python run_cli.py posts
```

### 2. Local Web Dashboard
Launch the web interface:
```bash
python run_web.py
```
Then open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

Features included in the Web UI:
- Quick test query presets (`IIUI`, `COMSATS`, `NUST`, `"International Islamic University"`).
- Search filters: Result limit (10, 20, 50, 100) and tab (`Latest` / `Top`).
- One-click JSON Export of search results.
- Live database viewer and search query history.
- Modal for inspecting full raw JSON payloads from X.

---

## 🧪 Running Tests

Run the comprehensive unit test suite:
```bash
pytest -v
```
All tests verify model serialization, parser accuracy, SQLite deduplication, and error trapping for missing accounts and network issues.
