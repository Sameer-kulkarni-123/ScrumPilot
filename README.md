# ScrumPilot 🤖🎙️

ScrumPilot is an automated meeting assistant designed to join Google Meet sessions, record system audio via loopback, and generate transcriptions using Whisper AI.

---

## 📁 Project Structure

```text
ScrumPilot/
├── backend/
│   ├── speech/                 # Audio capture & Transcription
│   │   ├── meet_bot.py         # Main: Joins Meet & records system audio
│   │   └── whisperai/
│   │       ├── live_transcript.py   # Real-time transcription (faster-whisper)
│   │       └── transcribe.py        # File-based transcription (openai-whisper)
│   │
│   ├── agents/                 # AI Intelligence
│   │
│   ├── tools/                  # Integrations & Scripts
│   │   ├── jira_client.py      # Jira API wrapper functions
│   │   └── test_jira.py        # Diagnostic tool for connection
│   │
│   ├── storage/                # RAG & Database logic
│
├── experiments/
│   └── PyAudioWPatchTest.py    # Audio diagnostic tool
│
└── requirements.txt
```

# 🚀 Setup & Usage

## 1. Environment Setup

Install the dependencies and set up the browser automation tools:

```bash
pip install -r requirements.txt
```

## 2. Configuration (.env)

Create a `.env` file in the root directory. Use the following guide to retrieve your credentials. **Never share your API tokens.**

| Variable | Where to find it |
|---|---|
| **JIRA_URL** | The base domain in your browser address bar. Example: `https://yourname.atlassian.net` (Do not include paths like `/projects/...`). |
| **JIRA_EMAIL** | The email address you use to log in to your Atlassian/Jira account. |
| **JIRA_API_TOKEN** | Go to **Atlassian API Tokens**. Click **Create API token**, label it `ScrumPilot`, and copy the secret. |
| **JIRA_PROJECT_KEY** | Look at any task on your board (e.g., `KAN-1`). The letters before the hyphen (`KAN`) are your project key.  In our project rn it is KAN|

### Template

```env
# JIRA CONFIG
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=KAN
```
## 3. Verification

Before running the full bot, verify your Jira connection and API permissions:

```bash
python backend/tools/test_jira.py
```