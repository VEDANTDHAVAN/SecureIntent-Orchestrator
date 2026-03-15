/**
 * content.js — SecureIntent Gmail Content Script
 *
 * Strategy:
 *  - Injects a fixed floating "🔍 Analyze" button (bottom-right)
 *    that is ALWAYS visible on Gmail — no toolbar selector dependency.
 *  - Detects when user opens an email via MutationObserver.
 *  - On button click: extracts subject + body + sender, calls /analyze
 *    via background.js, renders result in a slide-in sidebar panel.
 */

(function () {
    "use strict";

    // ── State ─────────────────────────────────────────────────────────────────
    let currentPanel = null;
    let observer = null;
    let lastSubject = "";
    let fabInjected = false;

    // ── Gmail DOM selectors ───────────────────────────────────────────────────
    // Multiple fallbacks — Gmail changes its DOM frequently
    const SUBJECT_SELECTORS = ["h2.hP", "h1.ha", "[data-legacy-thread-id] h2", ".nH h2"];
    const BODY_SELECTORS = ["div.a3s.aiL", "div.ii.gt div", ".a3s"];
    const SENDER_SELECTORS = ["span[email]", ".gD", "span[data-hovercard-id]"];
    const THREAD_SELECTORS = ["[data-legacy-thread-id]", ".nH [data-thread-id]"];
    const MSG_SELECTORS = ["[data-legacy-message-id]", ".nH [data-message-id]"];

    // ── Helpers ───────────────────────────────────────────────────────────────

    function trySelect(selectors) {
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) return el;
        }
        return null;
    }

    function extractSubject() {
        return trySelect(SUBJECT_SELECTORS)?.innerText?.trim() || "";
    }

    function extractBody() {
        const els = BODY_SELECTORS.flatMap((s) => [...document.querySelectorAll(s)]);
        return els[0]?.innerText?.trim() || "";
    }

    function extractSender() {
        for (const sel of SENDER_SELECTORS) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const email =
                el.getAttribute("email") ||
                el.getAttribute("data-hovercard-id") ||
                el.innerText?.match(/[\w.+\-]+@[\w\-]+\.[\w.]+/)?.[0];
            if (email) return email;
        }
        return "";
    }

    function extractThreadId() {
        for (const sel of THREAD_SELECTORS) {
            const el = document.querySelector(sel);
            const id = el?.getAttribute("data-legacy-thread-id") ||
                el?.getAttribute("data-thread-id");
            if (id) return id;
        }
        return "";
    }

    function extractMessageId() {
        for (const sel of MSG_SELECTORS) {
            const el = document.querySelector(sel);
            const id = el?.getAttribute("data-legacy-message-id") ||
                el?.getAttribute("data-message-id");
            if (id) return id;
        }
        return "";
    }

    function escapeHtml(str) {
        const d = document.createElement("div");
        d.textContent = String(str);
        return d.innerHTML;
    }

    /**
     * safeSend — wraps chrome.runtime.sendMessage to handle the
     * "Extension context invalidated" error that occurs when the
     * background service worker restarts while this tab is still open.
     * Shows a reload prompt instead of a cryptic error.
     */
    async function safeSend(msg) {
        // Guard: chrome.runtime becomes undefined when Chrome invalidates the
        // extension context (e.g. after a service worker restart or extension reload).
        // Must check BEFORE calling sendMessage, not inside the catch.
        if (!chrome?.runtime?.sendMessage) {
            showContextInvalidatedBanner();
            throw new Error("__context_invalidated__");
        }
        try {
            const result = await chrome.runtime.sendMessage(msg);
            // Chrome sets lastError if the background didn't respond cleanly
            if (chrome.runtime?.lastError) {
                const err = chrome.runtime.lastError.message || "";
                if (err.includes("context invalidated") || err.includes("receiving end")) {
                    showContextInvalidatedBanner();
                    throw new Error("__context_invalidated__");
                }
                throw new Error(err);
            }
            return result;
        } catch (e) {
            if (
                e.message === "__context_invalidated__" ||
                (e.message && (
                    e.message.includes("context invalidated") ||
                    e.message.includes("receiving end") ||
                    e.message.includes("Cannot read properties of undefined")
                ))
            ) {
                showContextInvalidatedBanner();
                throw new Error("__context_invalidated__");
            }
            throw e;
        }
    }

    function showContextInvalidatedBanner() {
        // Avoid duplicate banners
        if (document.getElementById("si-ctx-banner")) return;
        const banner = document.createElement("div");
        banner.id = "si-ctx-banner";
        Object.assign(banner.style, {
            position: "fixed",
            bottom: "96px",        // above the FAB
            right: "28px",
            zIndex: "2147483646",
            background: "#1a1f2e",
            border: "1px solid #f6ad55",
            borderRadius: "10px",
            padding: "12px 16px",
            fontSize: "12px",
            color: "#f6ad55",
            maxWidth: "260px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
            lineHeight: "1.5",
        });
        banner.innerHTML = `
          <strong>⚠️ SecureIntent reloaded</strong><br>
          The extension was updated while this tab was open.<br>
          <a id="si-ctx-reload" href="#" style="color:#7c8cf8;text-decoration:underline;cursor:pointer">
            Reload this tab to reconnect →
          </a>
          <button id="si-ctx-dismiss" style="float:right;background:none;border:none;color:#4a5568;cursor:pointer;font-size:14px;margin-left:8px">✕</button>
        `;
        document.body.appendChild(banner);
        document.getElementById("si-ctx-reload")?.addEventListener("click", (e) => {
            e.preventDefault();
            location.reload();
        });
        document.getElementById("si-ctx-dismiss")?.addEventListener("click", () => banner.remove());
    }

    // ── Floating Action Button ────────────────────────────────────────────────

    function injectFAB() {
        if (fabInjected || document.getElementById("si-fab")) return;
        fabInjected = true;

        const fab = document.createElement("button");
        fab.id = "si-fab";
        fab.title = "SecureIntent: Analyze this email";
        fab.innerHTML = "🔍";
        fab.setAttribute("aria-label", "Analyze email with SecureIntent");

        Object.assign(fab.style, {
            position: "fixed",
            bottom: "28px",
            right: "28px",
            zIndex: "2147483647",           // max z-index
            width: "52px",
            height: "52px",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #667eea, #764ba2)",
            color: "white",
            fontSize: "22px",
            border: "none",
            cursor: "pointer",
            boxShadow: "0 4px 20px rgba(102,126,234,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "transform 0.15s, box-shadow 0.15s",
            lineHeight: "1",
            padding: "0",
        });

        fab.addEventListener("mouseenter", () => {
            fab.style.transform = "scale(1.1)";
            fab.style.boxShadow = "0 6px 28px rgba(102,126,234,0.7)";
        });
        fab.addEventListener("mouseleave", () => {
            fab.style.transform = "scale(1.0)";
            fab.style.boxShadow = "0 4px 20px rgba(102,126,234,0.5)";
        });

        fab.addEventListener("click", handleAnalyzeClick);
        document.body.appendChild(fab);
    }

    // ── Sidebar Panel ─────────────────────────────────────────────────────────

    function showPanel(contentEl) {
        removePanel();

        const panel = document.createElement("div");
        panel.id = "si-panel";
        panel.className = "si-panel";

        panel.innerHTML = `
          <div class="si-panel-header">
            <span class="si-panel-title">🔐 SecureIntent</span>
            <button class="si-close-btn" id="si-close">✕</button>
          </div>
        `;
        panel.appendChild(contentEl);

        document.body.appendChild(panel);
        currentPanel = panel;

        document.getElementById("si-close").addEventListener("click", removePanel);
    }

    function removePanel() {
        if (currentPanel) { currentPanel.remove(); currentPanel = null; }
    }

    // ── State UIs ────────────────────────────────────────────────────────────

    function loadingEl() {
        const el = document.createElement("div");
        el.className = "si-loading";
        el.innerHTML = `<div class="si-spinner"></div><p>Analyzing email…</p>`;
        return el;
    }

    function errorEl(msg) {
        const el = document.createElement("div");
        el.className = "si-error";

        // Detect 401 Unauthorized or expired token
        const isAuthError = msg.includes("401") || msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("invalid token");

        if (isAuthError) {
            el.innerHTML = `
              <p>🔑 Your session has expired.</p>
              <button id="si-relogin-btn" style="
                background: #7c8cf8; color: white; border: none; padding: 8px 16px;
                border-radius: 6px; font-weight: 600; cursor: pointer; margin-top: 8px;
                width: 100%; font-size: 13px;
              ">Sign In to Continue</button>
            `;
            el.querySelector("#si-relogin-btn").addEventListener("click", () => {
                chrome.runtime.sendMessage({ type: "START_LOGIN" });
            });
        } else {
            el.innerHTML = `<p>⚠️ ${escapeHtml(msg)}</p>`;
        }
        return el;
    }

    function resultEl(data) {
        const intent = data.intent || {};
        const risk = data.risk_score || {};
        const policy = (data.policy_decision || "allow").toLowerCase();
        const plan = data.goal_plan || {};
        const steps = plan.steps || data.goal_plan?.steps || [];
        const planId = data.plan_id || null;
        const reasons = risk.reasons || [];
        const summary = plan.summary || "";
        const triggeredRules = (data.triggered_rules || []).join(", ");
        const explanation = data.policy_explanation || "";

        const riskLevel = (risk.level || "unknown").toLowerCase();
        const badgeClass = { low: "si-badge-low", medium: "si-badge-medium", high: "si-badge-high", critical: "si-badge-critical" }[riskLevel] || "si-badge-unknown";
        const policyClass = { allow: "si-policy-allow", require_approval: "si-policy-approval", block: "si-policy-block" }[policy] || "";
        const policyLabel = { allow: "✅ Auto-allowed", require_approval: "⏳ Requires Your Approval", block: "🚫 Blocked by Policy" }[policy] || policy;

        const actionEmoji = {
            gmail_send_reply: "📤 Send Reply", gmail_send_email: "📧 Send Email",
            gmail_forward: "↗️ Forward", gmail_create_draft: "📝 Draft",
            calendar_create_event: "📅 Create Event", calendar_update_event: "📅 Update Event",
            calendar_cancel_event: "🗑 Cancel Event", calendar_check_availability: "🔍 Check Avail.",
            payment_verify: "🔐 Verify", payment_initiate: "💸 Initiate Payment",
            invoice_request: "🧾 Invoice",
            task_create: "✅ Create Task", task_assign: "👤 Assign", task_update: "🔄 Update", task_escalate: "🚨 Escalate",
            doc_request: "📂 Get Doc", doc_share: "🔗 Share", doc_summarize: "📋 Summarize",
            approval_request: "⏳ Request Approval", approval_send: "✅ Send Approval",
            notify_stakeholder: "🔔 Notify", escalate_manager: "🚨 Escalate",
            telegram_send_message: "Telegram Message",
            human_review: "👁 Human Review", log_only: "📊 Log",
        };

        const reasonsHtml = reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("");
        const stepsHtml = steps.map((s, i) => {
            const actionKey = (s.action || "log_only").toLowerCase();
            const label = actionEmoji[actionKey] || actionKey.replace(/_/g, " ");
            const apiBadge = s.requires_external_action
                ? `<span class="si-step-badge" style="background:#1a2a3a;color:#63b3ed">🌐 API</span>` : "";
            const approvalBadge = s.requires_human_approval
                ? `<span class="si-step-badge">👤 Approval</span>` : "";
            return `
              <div class="si-step">
                <span class="si-step-num">${i + 1}</span>
                <div style="flex:1;min-width:0">
                  <div style="font-size:10px;color:#7c8cf8;font-weight:600;margin-bottom:2px">${escapeHtml(label)}</div>
                  <div class="si-step-action">${escapeHtml(s.description || "")}</div>
                </div>
                ${approvalBadge}${apiBadge}
              </div>`;
        }).join("");

        const el = document.createElement("div");
        el.className = "si-result";
        el.innerHTML = `
          <div class="si-section">
            <div class="si-row">
              <span class="si-label">Intent</span>
              <span class="si-value">${escapeHtml((intent.intent_type || "—").replace(/_/g, " "))}</span>
            </div>
            <div class="si-row">
              <span class="si-label">Confidence</span>
              <span class="si-value">${((intent.confidence_score || 0) * 100).toFixed(0)}%</span>
            </div>
            ${summary ? `<div style="font-size:11px;color:#a0aec0;margin-top:5px;font-style:italic">${escapeHtml(summary)}</div>` : ""}
          </div>

          <div class="si-section">
            <div class="si-row">
              <span class="si-label">Risk</span>
              <span class="si-badge ${badgeClass}">${riskLevel.toUpperCase()}</span>
              <span class="si-risk-score">${((risk.score || 0) * 100).toFixed(0)}/100</span>
            </div>
            ${reasonsHtml ? `<ul class="si-reasons">${reasonsHtml}</ul>` : ""}
          </div>

          <div class="si-section">
            <div class="si-policy-banner ${policyClass}">${policyLabel}</div>
            ${triggeredRules ? `<div style="font-size:11px;color:#718096;margin-top:6px;text-align:center">Rules: ${escapeHtml(triggeredRules)}</div>` : ""}
            ${explanation ? `<div style="font-size:11px;color:#a0aec0;margin-top:4px;text-align:center">${escapeHtml(explanation)}</div>` : ""}
          </div>

          ${stepsHtml ? `
          <div class="si-section">
            <div class="si-label" style="margin-bottom:8px">Workflow · ${steps.length} step${steps.length !== 1 ? "s" : ""}</div>
            <div class="si-steps">${stepsHtml}</div>
          </div>` : ""}

          ${planId && policy === "require_approval" ? (function () {
                // Detect if this is a calendar-type plan for the smart button
                const calendarGoals = [
                    "schedule_calendar_event", "reschedule_event", "cancel_event"
                ];
                const isCalendarPlan = calendarGoals.includes((plan.goal_type || "").toLowerCase()) ||
                    steps.some(s => (s.action || "").startsWith("calendar_"));

                if (isCalendarPlan) {
                    return `
              <div class="si-actions" id="si-actions-${planId}">
                <button class="si-btn-calendar" data-plan-id="${planId}">
                  📅 Approve &amp; Add to Calendar
                </button>
                <button class="si-btn-block" data-plan-id="${planId}">🚫 Block</button>
                <button class="si-btn-dryrun" data-plan-id="${planId}">👁 Preview</button>
              </div>`;
                }

                return `
            <div class="si-actions" id="si-actions-${planId}">
              <button class="si-btn-approve" data-plan-id="${planId}">✅ Approve</button>
              <button class="si-btn-block"   data-plan-id="${planId}">🚫 Block</button>
              <button class="si-btn-dryrun"  data-plan-id="${planId}">👁 Preview</button>
            </div>`;
            })() : ""}

          ${policy === "allow" ? `<div class="si-auto-note">ℹ️ This workflow would auto-execute based on policy.</div>` : ""}
          ${policy === "block" ? `<div class="si-auto-note" style="color:#fc8181">🛑 Blocked — no action will be taken.</div>` : ""}
        `;

        el.querySelector(".si-btn-calendar")?.addEventListener("click", () => handleApproveAndCalendar(planId, el));
        el.querySelector(".si-btn-approve")?.addEventListener("click", () => handleApprove(planId, el));
        el.querySelector(".si-btn-block")?.addEventListener("click", () => handleBlock(planId, el));
        el.querySelector(".si-btn-dryrun")?.addEventListener("click", () => handleDryRun(planId, el));

        return el;
    }

    // ── Analyze click ────────────────────────────────────────────────────────

    async function handleAnalyzeClick() {
        const subject = extractSubject();
        const body = extractBody();
        const sender = extractSender();
        const thread_id = extractThreadId();
        const message_id = extractMessageId();

        if (!subject && !body) {
            showPanel(errorEl("Could not read email — please open a full email first."));
            return;
        }

        showPanel(loadingEl());

        try {
            const result = await safeSend({
                type: "EXTRACT_INTENT",
                subject,
                body,
                sender,
                thread_id,
                message_id,
            });

            if (!result || result.error) {
                showPanel(errorEl(result?.error || "No response from backend. Is Docker running?"));
            } else {
                showPanel(resultEl(result));
            }
        } catch (err) {
            if (err.message !== "__context_invalidated__") {
                const msg = err.message || "";
                if (msg.includes("401") || msg.toLowerCase().includes("expired")) {
                    showPanel(errorEl("401: Session expired"));
                } else {
                    showPanel(errorEl(msg || "Extension error — check chrome://extensions for errors."));
                }
            }
        }
    }

    // ── Action handlers ──────────────────────────────────────────────────────

    function setLoading(container, on) {
        const a = container.querySelector("[id^='si-actions'], .si-actions");
        if (a) { a.style.opacity = on ? "0.5" : "1"; a.style.pointerEvents = on ? "none" : "auto"; }
    }

    function replaceActions(container, html) {
        const a = container.querySelector("[id^='si-actions'], .si-actions");
        if (a) a.outerHTML = html;
    }

    async function handleApprove(planId, container) {
        setLoading(container, true);
        try {
            const r = await safeSend({ type: "APPROVE_PLAN", planId });
            if (r.error) throw new Error(r.error);
            replaceActions(container, `
              <div class="si-approved-banner">✅ Approved — awaiting execution</div>
              <div class="si-actions">
                <button class="si-btn-execute" data-plan-id="${planId}">▶️ Execute Now</button>
              </div>
            `);
            container.querySelector(".si-btn-execute")?.addEventListener("click", () => handleExecute(planId, container));
        } catch (e) {
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        }
    }

    async function handleApproveAndCalendar(planId, container) {
        setLoading(container, true);
        try {
            const r = await safeSend({ type: "APPROVE_AND_EXECUTE", planId });
            if (r.error) throw new Error(r.error);

            const succeeded = r.steps_succeeded ?? r.steps_total ?? 0;
            const total = r.steps_total ?? 0;
            const calLink = r.calendar_event_link;

            const viewBtn = calLink
                ? `<a class="si-cal-link" href="${calLink}" target="_blank">📅 View in Google Calendar →</a>`
                : "";

            replaceActions(container, `
              <div class="si-success">✅ Added to Google Calendar (${succeeded}/${total} steps succeeded)</div>
              ${viewBtn}
            `);
        } catch (e) {
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        }
    }

    async function handleExecute(planId, container) {
        setLoading(container, true);
        try {
            const r = await safeSend({ type: "EXECUTE_PLAN", planId });
            if (r.error) throw new Error(r.error);
            const succeeded = r.steps_succeeded ?? r.steps_total;
            const total = r.steps_total ?? 0;
            replaceActions(container, `
              <div class="si-success">✅ Executed — ${succeeded}/${total} steps succeeded</div>
              <div class="si-report-row">
                <button class="si-btn-report" data-plan-id="${planId}">📄 Download Report (Google Docs)</button>
              </div>
            `);
            container.querySelector(".si-btn-report")?.addEventListener("click", () => handleReport(planId, container));
        } catch (e) {
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        }
    }

    async function handleReport(planId, container) {
        const btn = container.querySelector(".si-btn-report");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "⏳ Generating report…";
        }

        try {
            const r = await safeSend({ type: "GENERATE_REPORT", planId });
            if (r?.error) throw new Error(r.error);
            if (!r?.doc_url) throw new Error("No doc URL returned");
            window.open(r.doc_url, "_blank", "noopener,noreferrer");
        } catch (e) {
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "📄 Download Report (Google Docs)";
            }
        }
    }

    async function handleBlock(planId, container) {
        setLoading(container, true);
        try {
            const r = await safeSend({ type: "REJECT_PLAN", planId });
            if (r.error) throw new Error(r.error);
            replaceActions(container, `<div class="si-blocked">🚫 Plan blocked and logged.</div>`);
        } catch (e) {
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        }
    }

    async function handleDryRun(planId, container) {
        setLoading(container, true);
        try {
            const r = await safeSend({ type: "DRY_RUN", planId });
            if (r.error) throw new Error(r.error);
            const stepsHtml = (r.steps || [])
                .map(s => `<div class="si-dry-step"><strong>${escapeHtml(s.action)}</strong>: ${escapeHtml(s.description || "")}</div>`)
                .join("");
            replaceActions(container, `
              <div class="si-dry-run-result">
                <div class="si-dry-header">👁 Preview (No Real Actions)</div>
                <div class="si-dry-summary">${escapeHtml(r.summary || "")}</div>
                ${stepsHtml}
              </div>
              <div class="si-actions">
                <button class="si-btn-approve" data-plan-id="${planId}">✅ Approve</button>
                <button class="si-btn-block"   data-plan-id="${planId}">🚫 Block</button>
              </div>
            `);
            container.querySelector(".si-btn-approve")?.addEventListener("click", () => handleApprove(planId, container));
            container.querySelector(".si-btn-block")?.addEventListener("click", () => handleBlock(planId, container));
        } catch (e) {
            setLoading(container, false);
            replaceActions(container, `<div class="si-error">❌ ${escapeHtml(e.message)}</div>`);
        }
    }

    // ── Boot: inject FAB only ─────────────────────────────────────────────────
    // Auto-analyze is intentionally DISABLED — analysis fires only on FAB click.
    // The MutationObserver only re-injects the FAB if Gmail's SPA removes it.

    let autoAnalyzeTimer = null;

    function init() {
        injectFAB();

        // Seed lastSubject so a page reload with an already-open email
        // is NOT treated as a "new" email navigation
        lastSubject = extractSubject();

        // Keep the FAB alive across Gmail SPA navigations
        observer = new MutationObserver(() => {
            injectFAB();
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "complete" || document.readyState === "interactive") {
        init();
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
