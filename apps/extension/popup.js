/**
 * popup.js — SecureIntent Extension Popup
 *
 * Manages 3 screens:
 *   screen-login   → no JWT stored
 *   screen-waiting → OAuth tab opened (shows on NEXT popup open)
 *   screen-home    → JWT stored, user logged in
 *
 * NOTE: Chrome closes the popup the moment a new tab opens.
 * The "waiting" screen is only visible if the user re-opens the popup
 * while the OAuth tab is still open. That is normal Chrome behaviour.
 */

const $ = (id) => document.getElementById(id);

// ── Screen management ──────────────────────────────────────────────────────────

function showScreen(id) {
    ["screen-login", "screen-waiting", "screen-home"].forEach((s) => {
        const el = $(s);
        if (el) el.classList.toggle("active", s === id);
    });
}

function showLoginError(msg) {
    let el = $("login-error");
    if (!el) {
        el = document.createElement("p");
        el.id = "login-error";
        el.style.cssText =
            "color:#fc8181;font-size:11px;text-align:center;margin-top:10px;padding:6px 8px;background:rgba(252,129,129,0.1);border-radius:6px;";
        $("screen-login").appendChild(el);
    }
    el.textContent = msg;
}

function clearLoginError() {
    const el = $("login-error");
    if (el) el.remove();
}

// ── Message helpers ────────────────────────────────────────────────────────────

async function sendMsg(msg) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(msg, (response) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else {
                resolve(response);
            }
        });
    });
}

// ── Init ───────────────────────────────────────────────────────────────────────

async function init() {
    let settings;
    try {
        settings = await sendMsg({ type: "GET_SETTINGS" });
    } catch (e) {
        showLoginError("Background script not responding. Reload the extension.");
        return;
    }

    // Fill API URL
    if ($("api-url-input")) $("api-url-input").value = settings.apiUrl || "http://localhost:8000";

    // If a JWT is stored, go straight to home
    if (settings.jwtToken) {
        showScreen("screen-home");
        renderHome(settings);
        return;
    }

    // If background marked an OAuth login as pending, show waiting screen
    if (settings.oauthPending) {
        showScreen("screen-waiting");
        return;
    }

    showScreen("screen-login");
}

// ── Home screen ────────────────────────────────────────────────────────────────

async function renderHome(settings) {
    if ($("user-email")) {
        $("user-email").textContent = settings.userEmail || "Authenticated User";
    }
    checkConnection(settings.apiUrl);
    loadDashboard(settings);
}

async function checkConnection(apiUrl) {
    const dot = $("status-dot");
    const txt = $("status-text");
    if (!dot || !txt) return;

    try {
        const result = await sendMsg({ type: "CHECK_CONNECTION" });
        if (result?.connected) {
            dot.className = "status-dot connected";
            txt.textContent = `Connected · ${(result.apiUrl || apiUrl).replace("http://", "")}`;
        } else {
            dot.className = "status-dot disconnected";
            txt.textContent = "Backend unreachable — is Docker running?";
        }
    } catch {
        dot.className = "status-dot disconnected";
        txt.textContent = "Backend unreachable";
    }
}

async function loadDashboard(settings) {
    const apiUrl = settings.apiUrl || "http://localhost:8000";
    const token = settings.jwtToken;
    const headers = token ? { "Authorization": `Bearer ${token}` } : {};

    // Load pending plans
    try {
        const resp = await fetch(`${apiUrl}/plans/pending`, { headers });
        if (resp.ok) {
            const data = await resp.json();
            const count = data.count || 0;
            const banner = $("pending-banner");
            if (banner) {
                if (count > 0) {
                    banner.style.display = "flex";
                    $("pending-count").textContent = count;
                } else {
                    banner.style.display = "none";
                }
            }
        }
    } catch { /* pending fetch failed — non-fatal */ }

    // Load history
    try {
        const resp = await fetch(`${apiUrl}/plans/history?limit=10`, { headers });
        if (resp.ok) {
            const data = await resp.json();
            renderHistory(data.plans || []);
        } else {
            renderHistory([]);
        }
    } catch {
        renderHistory([]);
    }
}

function renderHistory(plans) {
    const container = $("history-container");
    const loading = $("history-loading");
    if (loading) loading.remove();
    if (!container) return;

    if (!plans.length) {
        container.innerHTML = '<div class="empty-state">No executions yet.<br>Approve a plan to get started.</div>';
        return;
    }

    // Compute risk summary
    const counts = { high: 0, medium: 0, low: 0 };
    plans.forEach(p => {
        const lvl = (p.risk_level || "low").toLowerCase();
        if (counts[lvl] !== undefined) counts[lvl]++;
    });
    const riskCards = $("risk-cards");
    if (riskCards) {
        riskCards.style.display = "flex";
        $("risk-high").textContent = counts.high;
        $("risk-medium").textContent = counts.medium;
        $("risk-low").textContent = counts.low;
    }

    const statusIcon = {
        executed: "✅",
        rejected: "🚫",
        failed: "⚠️",
    };

    const items = plans.slice(0, 8).map(p => {
        const icon = statusIcon[p.status] || "•";
        const subject = esc(p.subject || "(no subject)");
        const when = p.created_at
            ? new Date(p.created_at).toLocaleDateString([], { month: "short", day: "numeric" })
            : "";
        const goal = esc((p.goal_type || "").replace(/_/g, " ").toLowerCase());
        const cls = p.status || "";
        const showReport = (p.status === "executed" || p.status === "failed");
        const reportBtn = showReport
            ? `<button class="btn-report" data-plan-id="${esc(p.id)}" title="Download Google Doc report">📄</button>`
            : "";
        return `
          <div class="history-item">
            <span class="history-icon">${icon}</span>
            <div class="history-info">
              <div class="history-subject">${subject}</div>
              <div class="history-meta">${goal} · ${when}</div>
            </div>
            <span class="history-status ${cls}">${p.status || ""}</span>
            ${reportBtn}
          </div>`;
    }).join("");

    container.innerHTML = `<div class="history-list">${items}</div>`;

    // Wire report buttons
    container.querySelectorAll(".btn-report").forEach(btn => {
        btn.addEventListener("click", () => downloadReport(btn));
    });
}

function esc(str) {
    const d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
}

// ── Report download ────────────────────────────────────────────────────────────

async function downloadReport(btn) {
    const planId = btn.dataset.planId;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = "⏳";

    try {
        const settings = await sendMsg({ type: "GET_SETTINGS" });
        const apiUrl = settings.apiUrl || "http://localhost:8000";
        const token = settings.jwtToken;

        const resp = await fetch(`${apiUrl}/plans/${planId}/report`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `API error ${resp.status}`);
        }
        const data = await resp.json();
        if (data.doc_url) {
            chrome.tabs.create({ url: data.doc_url });
        } else {
            throw new Error("No doc URL returned from server");
        }
    } catch (e) {
        alert("Report failed: " + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = orig;
    }
}

// ── Google Login button ────────────────────────────────────────────────────────

$("btn-google-login")?.addEventListener("click", async () => {
    clearLoginError();

    const apiUrl = ($("api-url-input")?.value?.trim()) || "http://localhost:8000";
    await chrome.storage.local.set({ apiUrl });

    // ── Step 1: test backend is reachable before opening OAuth tab ───────────
    const btn = $("btn-google-login");
    btn.textContent = "Checking backend…";
    btn.disabled = true;

    try {
        const resp = await fetch(`${apiUrl}/health`);
        if (!resp.ok) throw new Error(`Server replied ${resp.status}`);
    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 533.5 544.3" xmlns="http://www.w3.org/2000/svg">
        <path d="M533.5 278.4c0-18.5-1.5-37.1-4.7-55.3H272.1v104.8h147c-6.1 33.8-25.7 63.7-54.4 82.7v68h87.7c51.5-47.4 81.1-117.4 81.1-200.2z" fill="#4285f4"/>
        <path d="M272.1 544.3c73.4 0 135.3-24.1 180.4-65.7l-87.7-68c-24.4 16.6-55.9 26-92.6 26-71 0-131.2-47.9-152.8-112.3H28.9v70.1c46.2 91.9 140.3 149.9 243.2 149.9z" fill="#34a853"/>
        <path d="M119.3 324.3c-11.4-33.8-11.4-70.4 0-104.2V150H28.9c-38.6 76.9-38.6 167.5 0 244.4l90.4-70.1z" fill="#fbbc04"/>
        <path d="M272.1 107.7c38.8-.6 76.3 14 104.4 40.8l77.7-77.7C405 24.6 339.7-.8 272.1 0 169.2 0 75.1 58 28.9 150l90.4 70.1c21.5-64.5 81.8-112.4 152.8-112.4z" fill="#ea4335"/>
      </svg>
      Sign in with Google`;
        showLoginError(`❌ Can't reach backend at ${apiUrl} — is Docker running?`);
        return;
    }

    // ── Step 2: backend OK — fire START_LOGIN (tab opens, popup will close) ──
    try {
        await sendMsg({ type: "START_LOGIN" });
        // Chrome will close this popup when the tab opens. That's expected.
        // background.js will set oauthPending=true so next popup open shows waiting screen.
    } catch (err) {
        btn.disabled = false;
        showLoginError("Extension error: " + err.message);
    }
});

$("btn-save-url")?.addEventListener("click", () => {
    const apiUrl = $("api-url-input")?.value?.trim();
    if (apiUrl) chrome.storage.local.set({ apiUrl });
});

$("btn-logout")?.addEventListener("click", async () => {
    await sendMsg({ type: "LOGOUT" });
    showScreen("screen-login");
});

// ── Listen for background → popup LOGIN_SUCCESS notification ──────────────────
chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "_LOGIN_SUCCESS") {
        init();
    }
});

init();
