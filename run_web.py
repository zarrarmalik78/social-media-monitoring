#!/usr/bin/env python
"""Runner script for Social Media Monitoring Web Dashboard."""

import uvicorn

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" 🚀 Launching Social Media Monitoring Local Web Dashboard")
    print(" 🌐 Access URL: http://127.0.0.1:8000")
    print("=" * 60 + "\n")
    uvicorn.run("app.web.app:app", host="127.0.0.1", port=8000, reload=False)
