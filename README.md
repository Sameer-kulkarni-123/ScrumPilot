# ScrumPilot 🤖🎙️

ScrumPilot is an automated AI Scrum Master designed to join Google Meet sessions, record system audio, identify individual speakers (diarization), and automatically generate Jira tasks based on the meeting transcript.

---

## 📁 Project Structure

```text
ScrumPilot/
├── main.py                     # Main application entry point
├── backend/
│   ├── meeting/                # Automated Meeting Clients
│   │   └── meet_client.py      # Playwright bot for joining & monitoring Google Meet
│   ├── pipelines/              # End-to-end integration logic
│   │   └── meet_bot.py         # Coordinates meet joining, audio recording, and transcription
│   ├── speech/                 # Audio capture & Processing
│   │   ├── audio_recorder.py   # System audio recording via WASAPI loopback
│   │   ├── diarizer.py         # Task 1: Identifies WHO spoke (Pyannote)
│   │   ├── diarized_transcription.py # Master script: Combines Who + What
│   │   └── whisperai/
│   │       ├── live_transcript.py   # Real-time transcription (faster-whisper)
│   │       └── transcribe.py        # File-based transcription (openai-whisper)
│   │
│   ├── agents/                 # AI Intelligence (Scrum Agent logic)
│   │
│   ├── tools/                  # Integrations & Scripts
│   │   ├── jira_client.py      # Jira API wrapper functions
│   │   └── test_jira.py        # Diagnostic tool for connection
│   │
│   └── .env                    # Local credentials (git-ignored)
├── requirements.txt
└── README.md
```


# 🚀 Setup & Usage

## 1. Environment Setup

Install the dependencies and set up the browser automation tools:

```bash
pip install -r requirements.txt
```

## ❗ System Requirement: FFmpeg (Windows)

The speaker diarization system requires **FFmpeg DLLs** to be available in your system path.

### Steps

1. Download the **"full-shared" build** from:  
   https://www.gyan.dev/ffmpeg/builds/

2. Extract the archive to:

```text
C:\ffmpeg
```

3. Add the following directory to System Environment Variables → Path

```text
C:\ffmpeg\bin
```

4. Restart VS Code and your terminal.

## 2. Hugging Face Access (Required for Diarization)

The pyannote diarization models are gated. If access is not granted you will receive a 403 Forbidden error.

### Step 1 — Accept Model Terms

Visit the following pages while logged into Hugging Face and click "Agree and access repository".

https://huggingface.co/pyannote/segmentation-3.0

https://huggingface.co/pyannote/speaker-diarization-3.1

https://huggingface.co/pyannote/speaker-diarization-community-1

You may be asked to provide name and university details.

### Step 2 — Create a Hugging Face Token

1. Go to Hugging Face → Settings → Tokens
2. Click Create New Token
3. Select Read role
4. Copy the generated token

## 3. Configuration (.env)

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

HF_TOKEN=your_huggingface_read_token
OUTPUT_AUDIO_PATH=backend/speech/temp/meeting_audio.wav
```

## 4. Execution Workflow
### Step 1 — Record the Meeting

Run the main orchestrator script:
```bash
python main.py
```
The pipeline will:
1. **Automatically join the Google Meet** using Playwright.
2. **Start system audio recording** via `pyaudiowpatch`.
3. **Monitor participant lists** to remain in the meeting while active.
4. **Auto-leave** when the bot detects it has been alone for 30 consecutive seconds.
5. **Automatically transcribe** the completed audio recording into `transcript.txt`.

### Step 2 — Generate Diarized Transcript

Run:
```bash
python -m backend.speech.diarized_transcription
```
This script will:
- Load the recorded audio
- Run speaker diarization using Pyannote
- Transcribe speech using Whisper AI
- Produce a structured transcript file: `meeting_transcript.txt`

### Step 3 — Verify Jira Connection

Before running automation, verify that Jira credentials work:
```bash
python -m backend.tools.test_jira
```
This confirms:
- Jira API authentication
- Project access
- Permission to create issues

---

## ⚙️ Technical Documentation: Meeting Pipeline

The meeting capture and transcription process is designed as a modular pipeline, orchestrated by `backend.pipelines.meet_bot`.

### 1. The Pipeline Orchestrator (`pipelines/meet_bot.py`)
This script acts as the main entry point for the meeting pipeline. Running `python main.py` triggers `start_meet_bot()`, which handles:
- Starting the automated meeting client in the background.
- Triggering the system audio recording thread concurrently.
- Waiting for the meeting to conclude (auto-leave).
- Halting the audio recording gracefully.
- Passing the saved audio file to the Whisper AI module for transcription.

### 2. The Meeting Client (`meeting/meet_client.py`)
Responsible for browser automation using **Playwright**.
- Launches a persistent Chrome context and navigates to the Google Meet link.
- Automatically handles permissions, disables the microphone, enters a bot name, and joins the meeting.
- Continuously polls the participant list using multiple CSS and ARIA selector strategies to determine if the meeting is active.
- Leaves the meeting automatically if the bot remains alone for 30 consecutive seconds.

### 3. The Audio Recorder (`speech/audio_recorder.py`)
Captures raw system audio using **PyAudio** and the Windows WASAPI loopback device.
- Runs in a separate thread via `asyncio.to_thread` to prevent blocking the Playwright browser loop.
- Listens for a threading `Event` (`stop_event`) passed from the orchestrator to know exactly when to stop and save the `.wav` file.

### 4. Transcriber (`speech/whisperai/transcribe.py`)
Leverages **OpenAI's Whisper AI** model for post-meeting audio processing.
- Input: The high-quality `.wav` recording generated by the audio recorder.
- Output: A final text transcript saved to the specified output path.
- Handles the conversion of raw speech data into structured text once the meeting concludes.
