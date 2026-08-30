/**
 * Social Media Monitoring Prototype - Frontend Logic
 */

let currentPosts = [];
let savedPosts = [];

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  loadSavedPosts();
  loadHistory();
});

// Tab navigation
function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) {
    targetTab.classList.add("active");
  }

  // Highlight tab button
  const matchingBtn = Array.from(document.querySelectorAll(".tab-btn")).find((btn) =>
    btn.getAttribute("onclick").includes(tabId)
  );
  if (matchingBtn) {
    matchingBtn.classList.add("active");
  }

  if (tabId === "database") {
    loadSavedPosts();
  } else if (tabId === "history") {
    loadHistory();
  } else if (tabId === "accounts") {
    checkStatus();
  }
}

// Preset button clicked
function setQuery(text) {
  const input = document.getElementById("search-input");
  input.value = text;
  input.focus();
}

// Check pool readiness & DB stats
async function checkStatus() {
  const statusBadge = document.getElementById("status-badge");
  const statusText = document.getElementById("status-text");
  const warningBanner = document.getElementById("account-warning-banner");

  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    const ready = data.collector?.ready;
    const activeCount = data.collector?.active_accounts || 0;
    const totalCount = data.collector?.total_accounts || 0;
    const totalPosts = data.database?.total_posts || 0;

    // Update nav saved count
    document.getElementById("saved-count-nav").innerText = totalPosts;

    if (ready) {
      statusBadge.className = "status-badge status-ready";
      statusText.innerText = `Pool Ready (${activeCount} active)`;
      if (warningBanner) warningBanner.classList.add("hidden");
    } else {
      statusBadge.className = "status-badge status-warning";
      statusText.innerText = totalCount > 0 ? "Accounts Locked/Inactive" : "No Accounts Configured";
      if (warningBanner) warningBanner.classList.remove("hidden");
    }

    renderAccountsTable(data.collector?.accounts || []);
  } catch (err) {
    statusBadge.className = "status-badge status-warning";
    statusText.innerText = "API Offline";
  }
}

// Search submission
async function handleSearch(e) {
  e.preventDefault();
  const query = document.getElementById("search-input").value.trim();
  if (!query) return;

  const limit = parseInt(document.getElementById("search-limit").value, 10) || 20;
  const product = document.getElementById("search-tab").value || "Latest";
  const saveToDb = document.getElementById("save-db-toggle").checked;

  const loading = document.getElementById("search-loading");
  const errorBox = document.getElementById("search-error");
  const emptyState = document.getElementById("empty-state");
  const resultsHeader = document.getElementById("results-header");
  const postsContainer = document.getElementById("posts-container");
  const searchBtn = document.getElementById("search-btn");

  // Reset UI
  errorBox.classList.add("hidden");
  emptyState.classList.add("hidden");
  resultsHeader.classList.add("hidden");
  postsContainer.innerHTML = "";
  loading.classList.remove("hidden");
  searchBtn.disabled = true;

  const startTime = performance.now();

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        limit,
        product,
        save_to_db: saveToDb,
      }),
    });

    const data = await res.json();
    const duration = ((performance.now() - startTime) / 1000).toFixed(2);

    if (!res.ok) {
      const errDetail = data.detail;
      const isNoAccount = errDetail?.code === "NO_ACCOUNT";

      document.getElementById("error-title").innerText = isNoAccount
        ? "Account Session Required"
        : "Search Failed";
      document.getElementById("error-msg").innerText =
        typeof errDetail === "object" ? errDetail.message : (errDetail || "Unknown error occurred");
      document.getElementById("error-help").innerHTML = isNoAccount
        ? '<button class="btn btn-warning btn-sm" onclick="showAccountModal()" style="margin-top:8px;">Add Session Cookies Now</button>'
        : "";
      errorBox.classList.remove("hidden");
      return;
    }

    currentPosts = data.posts || [];

    // Update Header
    resultsHeader.classList.remove("hidden");
    document.getElementById("results-title").innerText = `Results for "${query}"`;
    document.getElementById("results-stats").innerText = `${currentPosts.length} posts found in ${duration}s ${
      saveToDb ? `(Saved ${data.saved_count || 0} to SQLite)` : ""
    }`;

    if (currentPosts.length === 0) {
      postsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📭</div>
          <h3>No posts found</h3>
          <p>No recent public posts matched the query "${query}". Try a different keyword.</p>
        </div>
      `;
    } else {
      renderPosts(currentPosts, postsContainer);
    }

    // Refresh DB counter
    checkStatus();
  } catch (err) {
    document.getElementById("error-title").innerText = "Network Error";
    document.getElementById("error-msg").innerText = err.message || "Failed to reach local server.";
    errorBox.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
    searchBtn.disabled = false;
  }
}

// Render list of post cards
function renderPosts(posts, container) {
  container.innerHTML = "";

  posts.forEach((post, index) => {
    const card = document.createElement("div");
    card.className = "post-card";

    const dateFormatted = new Date(post.created_at).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    const viewsHtml =
      post.views !== null && post.views !== undefined
        ? `<div class="metric-item views" title="Views">
             <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
             <span>${Number(post.views).toLocaleString()}</span>
           </div>`
        : "";

    const authorInitial = (post.author_name || post.author_username || "X")[0].toUpperCase();

    card.innerHTML = `
      <div class="post-header">
        <div class="post-author">
          <div class="author-avatar">${escapeHtml(authorInitial)}</div>
          <div class="author-names">
            <span class="author-name">${escapeHtml(post.author_name || post.author_username)}</span>
            <span class="author-username">@${escapeHtml(post.author_username)}</span>
          </div>
        </div>
        <span class="post-time">${dateFormatted}</span>
      </div>

      <div class="post-body">${escapeHtml(post.text)}</div>

      <div class="post-footer">
        <div class="post-metrics">
          <div class="metric-item likes" title="Likes">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
            <span>${Number(post.likes || 0).toLocaleString()}</span>
          </div>
          <div class="metric-item replies" title="Replies">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
            <span>${Number(post.replies || 0).toLocaleString()}</span>
          </div>
          <div class="metric-item reposts" title="Reposts">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
            <span>${Number(post.reposts || 0).toLocaleString()}</span>
          </div>
          ${viewsHtml}
        </div>

        <div class="post-actions">
          <button class="btn btn-secondary btn-sm" onclick="showRawPayload(${index})">Raw JSON</button>
          <a href="${escapeHtml(post.url)}" target="_blank" rel="noopener noreferrer" class="post-link">
            View on X ↗
          </a>
        </div>
      </div>
    `;

    container.appendChild(card);
  });
}

// Load saved posts from DB
async function loadSavedPosts() {
  const container = document.getElementById("saved-posts-container");
  const filterVal = document.getElementById("db-filter-input")?.value.trim() || "";

  try {
    const url = filterVal ? `/api/posts?q=${encodeURIComponent(filterVal)}` : "/api/posts?limit=100";
    const res = await fetch(url);
    const data = await res.json();
    savedPosts = data.posts || [];

    if (savedPosts.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📂</div>
          <h3>No saved posts found</h3>
          <p>Posts from your live searches will automatically appear here.</p>
        </div>
      `;
      return;
    }

    renderPosts(savedPosts, container);
  } catch (err) {
    container.innerHTML = `<div class="error-box">Failed to load saved posts: ${err.message}</div>`;
  }
}

function filterSavedPosts() {
  loadSavedPosts();
}

// Load Search History
async function loadHistory() {
  const container = document.getElementById("history-table-container");
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const history = data.history || [];

    if (history.length === 0) {
      container.innerHTML = `<p class="card-desc">No search history recorded yet.</p>`;
      return;
    }

    let html = `
      <table>
        <thead>
          <tr>
            <th>Query</th>
            <th>Platform</th>
            <th>Results</th>
            <th>Timestamp (UTC)</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
    `;

    history.forEach((item) => {
      html += `
        <tr>
          <td><strong>${escapeHtml(item.query)}</strong></td>
          <td>${escapeHtml(item.platform)}</td>
          <td>${item.results_count}</td>
          <td>${escapeHtml(item.searched_at)}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="repeatSearch('${escapeHtml(item.query)}')">Search Again</button>
          </td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p class="modal-error">Failed to load history: ${err.message}</p>`;
  }
}

function repeatSearch(query) {
  switchTab("search");
  document.getElementById("search-input").value = query;
  document.getElementById("search-form").dispatchEvent(new Event("submit"));
}

// Accounts table rendering
function renderAccountsTable(accounts) {
  const container = document.getElementById("accounts-table-container");
  if (!accounts || accounts.length === 0) {
    container.innerHTML = `<p class="card-desc" style="color: var(--accent-yellow);">No accounts registered in pool.</p>`;
    return;
  }

  let html = `
    <table>
      <thead>
        <tr>
          <th>Account / Identifier</th>
          <th>Logged In</th>
          <th>Active</th>
          <th>Total Requests</th>
          <th>Last Used</th>
          <th>Error Status</th>
        </tr>
      </thead>
      <tbody>
  `;

  accounts.forEach((acc) => {
    html += `
      <tr>
        <td><strong>${escapeHtml(acc.username || "unknown")}</strong></td>
        <td>${acc.logged_in ? "✅ Yes" : "❌ No"}</td>
        <td>${acc.active ? "✅ Yes" : "⚠️ Inactive/Locked"}</td>
        <td>${acc.total_req || 0}</td>
        <td>${escapeHtml(acc.last_used || "Never")}</td>
        <td>${escapeHtml(acc.error_msg || "None")}</td>
      </tr>
    `;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}

// Add Account Cookies
async function handleAddCookies(e) {
  e.preventDefault();
  const name = document.getElementById("cookie-account-name").value.trim();
  const cookies = document.getElementById("cookie-string").value.trim();
  const errBox = document.getElementById("cookie-modal-error");
  const submitBtn = document.getElementById("cookie-submit-btn");

  errBox.classList.add("hidden");
  submitBtn.disabled = true;

  try {
    const res = await fetch("/api/accounts/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, cookies }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to save cookies");
    }

    hideAccountModal();
    checkStatus();
    alert(`Account session '${name}' saved successfully!`);
  } catch (err) {
    errBox.innerText = err.message;
    errBox.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
  }
}

// Reset Locks
async function resetLocks() {
  try {
    const res = await fetch("/api/accounts/reset-locks", { method: "POST" });
    const data = await res.json();
    alert(data.message || "Locks reset.");
    checkStatus();
  } catch (err) {
    alert("Error resetting locks: " + err.message);
  }
}

// Modals
function showAccountModal() {
  document.getElementById("account-modal").classList.remove("hidden");
}
function hideAccountModal() {
  document.getElementById("account-modal").classList.add("hidden");
  document.getElementById("cookie-modal-error").classList.add("hidden");
}

function showRawPayload(index) {
  const post = currentPosts[index] || savedPosts[index];
  if (!post) return;
  document.getElementById("raw-modal-title").innerText = `Post ID: ${post.id} (JSON Payload)`;
  document.getElementById("raw-json-content").innerText = JSON.stringify(post, null, 2);
  document.getElementById("raw-modal").classList.remove("hidden");
}
function hideRawModal() {
  document.getElementById("raw-modal").classList.add("hidden");
}

// Export Results to JSON file
function exportResultsJSON() {
  if (!currentPosts || currentPosts.length === 0) return;
  const jsonStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentPosts, null, 2));
  const downloadAnchor = document.createElement("a");
  downloadAnchor.setAttribute("href", jsonStr);
  downloadAnchor.setAttribute("download", `x_search_results_${Date.now()}.json`);
  document.body.appendChild(downloadAnchor);
  downloadAnchor.click();
  downloadAnchor.remove();
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
