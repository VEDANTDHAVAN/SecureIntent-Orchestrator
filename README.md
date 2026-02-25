**SecureIntent Orchestrator** is a smart Chrome extension that seamlessly integrates with your Gmail and automates tasks by understanding the intent of your inbox emails. It leverages an Agentic Zero-Trust architecture to securely process, analyze, and execute actions, combining LLM-based intent extraction with a deterministic planning and execution engine.

---

## 🎯 The Problem
Email is the #1 vector for cyberattacks, yet it remains the primary hub for business workflows. Automating email tasks usually means giving "all-or-nothing" API access to poorly secured bots, leading to:
1.  **Security Risks**: Malicious emails triggering automated workflows (e.g., auto-forwarding sensitive data).
2.  **Lack of Control**: AI agents taking destructive actions without human oversight.
3.  **Fragmented Workflows**: Moving between email, calendar, and documents manually is time-consuming.

## 💡 The Solution
SecureIntent solves this by introducing a **Zero-Trust Intelligence Layer** for your inbox. It doesn't just "read and run"—it scrutinizes every email through a multi-stage security pipeline before a single line of code is executed.

---

## 🚀 Key Features

- **Zero-Trust Pipeline**: Every email undergoes rigorous risk scoring and policy checks before any action is planned or executed.
- **Intent Extraction**: Leverages LLMs to accurately identify the user's intent from email subjects and bodies.
- **Deterministic Planning**: Converts high-level intents into actionable, multi-step goal plans.
- **Secure Execution**: An orchestrator-led execution engine that interacts with external tools (Gmail, Google Docs, Calendar, Slack, etc.) via secure OAuth tokens.
- **Policy Guardrails**: Middleware that enforces safety rules, requiring human approval for high-risk or external actions.
- **Risk Scoring**: Automated analysis of SPF/DKIM records and URL scanning to detect phishing or malicious content.

## 🛠️ Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **AI/LLM**: [OpenAI GPT-4o](https://openai.com/)
- **Database**: [Supabase](https://supabase.com/) (PostgreSQL + Real-time)
- **Authentication**: JWT & Google OAuth 2.0
- **Tools & Integrations**: Google Workspace APIs (Gmail, Docs, Calendar), Slack API
- **Containerization**: Docker & Docker Compose

---

## 🏗️ Technical Architecture: The "Zero-Trust Pipeline"

SecureIntent ensures safety by passing every request through four distinct **Decision Gates**:

1.  **🛡️ Scrutinize (Risk Engine)**: Automated SPF/DKIM validation and URL scanning. If an email is suspicious, the pipeline stops immediately.
2.  **🧠 Extract (Intent Engine)**: LLMs (GPT-4o) parse raw email content into structured JSON intents.
3.  **📋 Plan (Planner)**: A deterministic engine converts intents into a sequence of tool-specific steps (e.g., "Create Draft", "Add to Calendar").
4.  **⚖️ Gatekeep (Policy Engine)**: Enforces rules (e.g., "External transfers always require human approval").
5.  **⚙️ Execute (Orchestrator)**: Carries out the final, approved plan via authenticated Google Workspace APIs.

---

## � Project Structure

```text
├── agents/             # Core AI logic (Intent extraction, Planning)
├── engines/            # Security & Policy engines (Risk scoring, Guardrails)
├── apps/               # Application entry points
│   ├── api/            # FastAPI backend (Routes, Schemas, Auth)
│   └── extension/      # Chrome Extension (Frontend/Logic)
├── tools/              # Tool implementations & Orchestrator dispatcher
├── shared/             # Shared utilities (Logging, Constants)
├── db/                 # Database models and connectivity
├── infra/              # Infrastructure and deployment (Docker)
└── sandbox/            # Isolated environment for safe tool execution
```

---

## 🚀 Judge's Fast Track (Quick Test)

To see the system in action as a judge, you can use our manual ingestion tool to bypass the real-time webhook requirement.

### 1. Quick API Setup
```bash
# Clone and install
git clone https://github.com/your-repo/SecureIntent-Orchestrator.git
cd SecureIntent-Orchestrator
pip install -r requirements.txt

# Run the API (Ensure .env is configured)
uvicorn apps.api.main:app --reload
```

### 2. The "Aha!" Moment (Manual Testing via Swagger)
1.  Navigate to `http://localhost:8000/docs`.
2.  Use the `POST /analyze` endpoint to simulate a Chrome extension call.
3.  **Input Sample**:
    ```json
    {
      "subject": "Can we meet tomorrow at 2pm?",
      "body": "Hi, I'd like to discuss the new project. Can we schedule a meeting?",
      "sender": "partner@example.com"
    }
    ```
4.  **Observe**: The response will show the **Risk Level**, the **Extracted Intent** (Meeting Request), and the **Generated Plan** (Search Calendar -> Propose Time).

---

## ⚙️ Detailed Setup & Installation

### 1. Backend Setup
- **Prerequisites**: Python 3.10+, Supabase account, OpenAI API Key.
- **Steps**:
  1. Create a virtual environment: `python -m venv venv`
  2. Activate: `source venv/bin/activate` (or `venv\Scripts\activate`)
  3. Install: `pip install -r requirements.txt`
  4. Configure: Copy `.env.example` to `.env` and fill the keys.
  5. Run: `uvicorn apps.api.main:app --reload`

### 2. Chrome Extension Setup
1.  Open Chrome and go to `chrome://extensions/`.
2.  Enable **Developer mode**.
3.  Click **Load unpacked** and select the `apps/extension` folder.
4.  Pin the extension and use it on any message in `mail.google.com`.

### 3. Gmail & Google Workspace Integration
- **GCP Project**: Enable Gmail API, Google Calendar API, and Google Docs API.
- **OAuth**: Configure an OAuth 2.0 Client ID (Web) with redirect URI `http://localhost:8000/auth/callback`.
- **Pub/Sub (Optional)**: Set up a topic and grant publish permissions for real-time push notifications.

---

## 🚀 How to Use the Chrome Extension

Once the backend is running and the extension is loaded, follow these steps to experience the full zero-trust pipeline:

### 1. Authentication
1.  Click the **SecureIntent icon** in your Chrome extensions bar.
2.  Ensure the **API URL** is correct (default: `http://localhost:8000`).
3.  Click **Sign in with Google**. A new tab will open for OAuth consent.
4.  Once authenticated, the tab will close, and the extension popup will show your email and connection status.

### 2. Analysis & Intent Extraction
1.  Navigate to **Gmail** (`mail.google.com`) and open any email.
2.  Locate the floating **🔍 Analyze** button at the bottom-right of your screen.
3.  Click the button. A sidebar will slide in, showing:
    - **Risk Score**: Security analysis of the sender and content.
    - **Intent**: What the AI thinks the sender wants.
    - **Proposed Plan**: Multi-step workflow generated by the agent.

### 3. Action & Execution
1.  If the policy requires approval, review the steps in the sidebar.
2.  Click **Approve** to authorize the workflow.
3.  Click **Execute Now** to carry out the actions (e.g., creating a draft, scheduling a meeting).
4.  Once finished, you can click **Download Report** to get a `.docx` summary or open the **Google Docs report** directly.

---

## 🧪 Testing
```bash
# Run the automated test suite
pytest
```
*Validated core logic across Intent Extraction, Planning, and Risk Scoring.*

---

## 📄 License
MIT License
