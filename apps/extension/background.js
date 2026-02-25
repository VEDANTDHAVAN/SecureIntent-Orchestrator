/**
 * background.js — SecureIntent Extension Service Worker
 *
 * Responsibilities:
 *  - Storage helpers for JWT, API URL, recent activity
 *  - Opens Google OAuth via /auth/login?source=extension
 *  - Monitors tabs: when /auth/callback completes, extracts JWT
 *    from the success page (window.__SI_TOKEN__) and auto-stores it
 *  - Message passing between content.js ↔ popup.js
 */

const DEFAULT_API_URL = "http://localhost:8000";

// ── Storage helpers ────────────────────────────────────────────────────────────

async function getSettings() {
    return new Promise((resolve) => {
        chrome.storage.local.get(
            ["apiUrl", "jwtToken", "userEmail", "recentActivity"],
            (data) => {
                resolve({
                    apiUrl: data.apiUrl || DEFAULT_API_URL,
                    jwtToken: data.jwtToken || null,
                    userEmail: data.userEmail || null,
                    recentActivity: data.recentActivity || [],
                });
            }
        );
    });
}

async function saveSettings(updates) {
    return new Promise((resolve) => chrome.storage.local.set(updates, resolve));
}

async function upsertExecutionHistory(entry) {
    return new Promise((resolve) => {
        chrome.storage.local.get(["executionHistory"], (data) => {
            const history = Array.isArray(data.executionHistory) ? data.executionHistory : [];
            const nowIso = new Date().toISOString();
            const normalized = {
                timestamp: entry.timestamp || nowIso,
                plan_id: entry.plan_id,
                status: entry.status,
                steps_total: entry.steps_total,
                steps_succeeded: entry.steps_succeeded,
                subject: entry.subject,
                goal_type: entry.goal_type,
                risk_level: entry.risk_level,
            };

            const idx = history.findIndex((h) => h && h.plan_id === normalized.plan_id);
            if (idx >= 0) {
                // Merge without overwriting existing fields with undefined
                const next = { ...history[idx] };
                Object.entries(normalized).forEach(([k, v]) => {
                    if (v !== undefined && v !== null && v !== "") next[k] = v;
                });
                history[idx] = next;
            } else {
                history.unshift(normalized);
            }

            const trimmed = history.slice(0, 20);
            chrome.storage.local.set({ executionHistory: trimmed }, () => resolve(trimmed));
        });
    });
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function apiRequest(path, options = {}) {
    const { apiUrl, jwtToken } = await getSettings();
    const headers = {
        "Content-Type": "application/json",
        ...(jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {}),
        ...(options.headers || {}),
    };
    const resp = await fetch(`${apiUrl}${path}`, { ...options, headers });
    if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`API ${resp.status}: ${err}`);
    }
    return resp.json();
}

// ── Recent activity log ────────────────────────────────────────────────────────

async function logActivity(entry) {
    const { recentActivity } = await getSettings();
    const updated = [
        { ...entry, timestamp: new Date().toISOString() },
        ...recentActivity,
    ].slice(0, 10);
    await saveSettings({ recentActivity: updated });
}

// ── OAuth login flow ───────────────────────────────────────────────────────────

// Tracks the tab opened for OAuth so we can close it after success
let _oauthTabId = null;

async function startOAuthLogin() {
    const { apiUrl } = await getSettings();
    const loginUrl = `${apiUrl}/auth/login?source=extension`;

    // Mark pending so popup shows waiting screen if re-opened
    await saveSettings({ oauthPending: true });

    // Open the OAuth tab
    const tab = await chrome.tabs.create({ url: loginUrl, active: true });
    _oauthTabId = tab.id;
}

// ── Tab monitor — capture JWT from the callback success page ──────────────────

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    // Only act when the tab finishes loading our callback success page
    if (changeInfo.status !== "complete") return;
    if (!tab.url) return;

    const { apiUrl } = await getSettings();
    const callbackPattern = `${apiUrl}/auth/callback`;

    if (!tab.url.startsWith(callbackPattern)) return;

    try {
        // Use world:"MAIN" to access variables set by the page's own script tag,
        // OR read from the #si-token DOM element (accessible from isolated world too).
        // We try both so either approach works.
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",   // Run in page's JS context — can read window.__SI_TOKEN__
            func: () => {
                return {
                    token: window.__SI_TOKEN__ || document.getElementById("si-token")?.dataset?.token || null,
                    email: window.__SI_EMAIL__ || document.getElementById("si-token")?.dataset?.email || null,
                };
            },
        });

        const { token, email } = results?.[0]?.result || {};

        if (token) {
            await saveSettings({ jwtToken: token, userEmail: email || "", oauthPending: false });
            await logActivity({ type: "login", email: email || "unknown" });

            // Close the OAuth tab
            chrome.tabs.remove(tabId);

            // Notify popup to refresh its UI
            chrome.runtime.sendMessage({ type: "_LOGIN_SUCCESS", email }).catch(() => { });
        }
    } catch (err) {
        console.warn("SecureIntent: Could not read token from callback tab:", err.message);
    }
});

// ── Message handler ────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    handleMessage(message, sender)
        .then(sendResponse)
        .catch((err) => sendResponse({ error: err.message }));
    return true;
});

async function handleMessage(message) {
    switch (message.type) {
        case "GET_SETTINGS":
            return getSettings();

        case "START_LOGIN":
            await startOAuthLogin();
            return { success: true };

        case "SAVE_TOKEN":
            await saveSettings({ jwtToken: message.token });
            return { success: true };

        case "LOGOUT":
            await saveSettings({ jwtToken: null, userEmail: null });
            return { success: true };

        case "CHECK_CONNECTION": {
            try {
                const { apiUrl } = await getSettings();
                const resp = await fetch(`${apiUrl}/health`);
                return { connected: resp.ok, apiUrl };
            } catch {
                return { connected: false };
            }
        }

        case "EXTRACT_INTENT": {
            const result = await apiRequest("/analyze", {
                method: "POST",
                body: JSON.stringify({
                    subject: message.subject,
                    body: message.body,
                    sender: message.sender || "",
                    thread_id: message.thread_id || "",
                    message_id: message.message_id || "",
                }),
            });
            await logActivity({
                type: "intent_extracted",
                subject: message.subject,
                intent: result.intent?.intent_type,
                risk: result.risk_score?.level,
                plan_id: result.plan_id,
            });
            // Seed local execution history with risk metadata so popup can display it
            if (result?.plan_id) {
                await upsertExecutionHistory({
                    plan_id: result.plan_id,
                    status: "aborted",
                    subject: message.subject,
                    goal_type: result.goal_plan?.goal_type,
                    risk_level: result.risk_score?.level,
                });
            }
            return result;
        }

        case "APPROVE_PLAN": {
            const result = await apiRequest(`/plans/${message.planId}/approve`, { method: "POST" });
            await logActivity({ type: "plan_approved", plan_id: message.planId });
            await upsertExecutionHistory({
                plan_id: message.planId,
                status: "approved",
            });
            return result;
        }

        case "REJECT_PLAN": {
            const result = await apiRequest(`/plans/${message.planId}/reject`, { method: "POST" });
            await logActivity({ type: "plan_rejected", plan_id: message.planId });
            await upsertExecutionHistory({
                plan_id: message.planId,
                status: "rejected",
            });
            return result;
        }

        case "APPROVE_AND_EXECUTE": {
            const result = await apiRequest(`/plans/${message.planId}/approve-and-execute`, { method: "POST" });
            await logActivity({ type: "plan_approved_and_executed", plan_id: message.planId });
            const normalizedStatus = (
                result.status === "failed" && (result.steps_succeeded || 0) > 0
            ) ? "executed" : (result.status || "executed");
            await upsertExecutionHistory({
                plan_id: message.planId,
                status: normalizedStatus,
                steps_total: result.steps_total,
                steps_succeeded: result.steps_succeeded,
            });
            return result;
        }

        case "EXECUTE_PLAN": {
            const result = await apiRequest(`/plans/${message.planId}/execute`, { method: "POST" });
            await logActivity({ type: "plan_executed", plan_id: message.planId });
            const normalizedStatus = (
                result.status === "failed" && (result.steps_succeeded || 0) > 0
            ) ? "executed" : (result.status || "executed");
            await upsertExecutionHistory({
                plan_id: message.planId,
                status: normalizedStatus,
                steps_total: result.steps_total,
                steps_succeeded: result.steps_succeeded,
            });
            return result;
        }

        case "DRY_RUN": {
            const result = await apiRequest(
                `/plans/${message.planId}/execute?dry_run=true`,
                { method: "POST" }
            );
            return result;
        }

        case "GENERATE_REPORT": {
            const result = await apiRequest(`/plans/${message.planId}/report`, { method: "GET" });
            await logActivity({ type: "report_generated", plan_id: message.planId });
            return result;
        }

        default:
            throw new Error(`Unknown message type: ${message.type}`);
    }
}
