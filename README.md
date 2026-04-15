# ScrumPilot - AI-Powered Scrum Assistant

An intelligent Scrum automation system that uses context-aware natural language processing to extract actionable items from meeting transcripts and manage them in Jira.

## Features

- Context-aware natural language processing for meeting transcripts
- LLM-powered extraction using Groq/Llama
- Telegram bot integration for approval workflow
- Complete Jira integration (epics, stories, tasks)
- PostgreSQL database for context management
- Three automated pipelines: Backlog, Sprint Planning, and Daily Standup

## Prerequisites

- Python 3.10 or higher
- PostgreSQL 14 or higher
- Git

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/your-username/ScrumPilot.git
cd ScrumPilot
```

### 2. Create Virtual Environment

**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup PostgreSQL Database

```bash
# Create database
createdb scrumpilot

# Or using psql
psql -U postgres
CREATE DATABASE scrumpilot;
\q
```

### 5. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Database
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/scrumpilot

# Groq API (https://console.groq.com)
GROQ_API_KEY=your_groq_api_key_here

# Jira (https://id.atlassian.com/manage-profile/security/api-tokens)
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=SP

# Telegram Bot (@BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### 6. Run Database Migrations

```bash
alembic upgrade head
```

### 7. Start the Backend

```bash
python -m backend.telegram.bot
```

The Telegram bot will start in polling mode and listen for commands.

## Usage

### Backlog Pipeline

Extracts epics from PM meetings, decomposes into stories/tasks, and calculates WSJF scores.

```bash
python run_backlog_pipeline.py
```

Process:
1. Extracts epics from PM meeting transcript
2. Decomposes epics into stories and tasks
3. Calculates WSJF scores for prioritization
4. Sends approval request to Telegram
5. Creates complete hierarchy in Jira after approval
6. Updates database with Jira keys

### Sprint Planning Pipeline

Plans sprints from meeting transcripts using natural language.

```bash
python run_sprint_planning_pipeline.py
```

Process:
1. Loads available backlog from database
2. Extracts sprint plan from meeting transcript
3. Maps natural language to Jira keys
4. Sends approval request to Telegram
5. Creates sprint and moves stories after approval

### Standup Pipeline

Updates task statuses from daily standup meetings.

```bash
python run_standup_pipeline.py
```

Process:
1. Loads active sprint items from database
2. Extracts status updates from standup transcript
3. Maps natural language to tasks
4. Updates Jira automatically

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Meeting Transcript                           │
│                      (Natural Language Input)                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Pipeline Orchestration                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Backlog    │  │    Sprint    │  │   Standup    │             │
│  │   Pipeline   │  │   Planning   │  │   Pipeline   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Context Loading Layer                             │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  Database Query Engine                                  │         │
│  │  • Load epics, stories, tasks with Jira keys           │         │
│  │  • Filter by status (exclude Done items)               │         │
│  │  • Include metadata (WSJF, priorities, assignments)    │         │
│  │  • Format as structured context for LLM                │         │
│  └────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LLM Processing Layer                              │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  Groq API (Llama 3.3 70B)                              │         │
│  │  • Receives: Transcript + Context                      │         │
│  │  • Performs: Semantic matching & entity extraction     │         │
│  │  • Returns: Structured JSON with Jira keys             │         │
│  └────────────────────────────────────────────────────────┘         │
│                                                                       │
│  Agents:                                                              │
│  • BacklogExtractor    - Extract epics from PM meetings              │
│  • EpicDecomposer      - Decompose epics into stories/tasks         │
│  • WSJFCalculator      - Calculate prioritization scores             │
│  • SprintPlanner       - Extract sprint planning decisions           │
│  • ScrumExtractor      - Extract standup status updates              │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Human-in-the-Loop (HITL) Layer                      │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  Telegram Bot Integration                               │         │
│  │  • Send approval request with extracted data           │         │
│  │  • PM/Scrum Master reviews and can edit               │         │
│  │  • Approve or reject with inline buttons               │         │
│  │  • Store approval decision in database                 │         │
│  └────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Jira Integration Layer                            │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  JiraCreatorAgent                                       │         │
│  │  • Create epics with WSJF scores                       │         │
│  │  • Create stories with acceptance criteria             │         │
│  │  • Create sub-tasks with estimates                     │         │
│  │  • Update task statuses and assignments                │         │
│  │  • Move items to sprints                               │         │
│  │  • Idempotency: Skip if already exists                 │         │
│  └────────────────────────────────────────────────────────┘         │
│                                                                       │
│  Jira API Operations:                                                 │
│  • POST /rest/api/3/issue        - Create issues                     │
│  • PUT  /rest/api/3/issue/{key}  - Update issues                     │
│  • POST /rest/agile/1.0/sprint   - Create sprints                    │
│  • POST /rest/agile/1.0/sprint/{id}/issue - Move to sprint           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Database Synchronization Layer                    │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  PostgreSQL Database (SQLAlchemy ORM)                  │         │
│  │  • Store created items with Jira keys                  │         │
│  │  • Update status and assignments                       │         │
│  │  • Track processing runs and approvals                 │         │
│  │  • Maintain context for future extractions             │         │
│  └────────────────────────────────────────────────────────┘         │
│                                                                       │
│  Tables:                                                              │
│  • meetings          - Meeting records                                │
│  • processing_runs   - Pipeline execution tracking                    │
│  • epics            - Epic items with WSJF scores                     │
│  • stories          - User stories with acceptance criteria           │
│  • tasks            - Sub-tasks with estimates                        │
│  • sprints          - Sprint records                                  │
│  • sprint_stories   - Many-to-many sprint-story mapping               │
│  • scrum_actions    - Standup action items                            │
│  • approval_requests - HITL approval workflow                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

#### 1. Backlog Pipeline Flow
```
PM Meeting Transcript
    → BacklogExtractor (LLM)
    → Extracted Epics with WSJF components
    → EpicDecomposer (LLM)
    → Stories & Tasks with estimates
    → WSJFCalculator
    → Prioritized backlog
    → Telegram Approval
    → JiraCreatorAgent
    → Jira Tickets Created
    → Database Sync
```

#### 2. Sprint Planning Flow
```
Sprint Planning Transcript
    → Load Backlog Context (Database)
    → SprintPlanningExtractor (LLM + Context)
    → Mapped Sprint Items with Jira Keys
    → Telegram Approval
    → Create Sprint in Jira
    → Move Stories to Sprint
    → Assign Tasks to Developers
    → Database Sync
```

#### 3. Standup Flow
```
Standup Transcript
    → Load Active Sprint Context (Database)
    → ScrumExtractor (LLM + Context)
    → Status Updates with Jira Keys
    → Update Jira Statuses
    → Update Assignments
    → Database Sync
```

### Component Interaction

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Pipeline   │────▶│   Agents     │────▶│   Database   │
│ Orchestrator │     │   (LLM)      │     │  (Context)   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                     │                     │
       │                     ▼                     │
       │             ┌──────────────┐             │
       │             │   Telegram   │             │
       │             │     Bot      │             │
       │             └──────────────┘             │
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│     Jira     │◀────│   Approval   │────▶│   Logging    │
│     API      │     │   Service    │     │   System     │
└──────────────┘     └──────────────┘     └──────────────┘
```

## Project Structure

```
ScrumPilot/
├── backend/
│   ├── agents/              # LLM agents for extraction
│   ├── db/                  # Database models and CRUD
│   ├── pipelines/           # Main pipelines
│   ├── telegram/            # Telegram bot handlers
│   └── tools/               # Jira client, utilities
├── alembic/                 # Database migrations
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
└── README.md
```

## Configuration

### Required API Keys

1. **Groq API** - https://console.groq.com
2. **Jira API Token** - https://id.atlassian.com/manage-profile/security/api-tokens
3. **Telegram Bot Token** - @BotFather on Telegram

### Database Configuration

Default: `postgresql://postgres:postgres@localhost:5432/scrumpilot`

## Testing

### Verify Installation

```bash
# Check database connection
python check_database_items.py

# List Jira tickets
python list_jira_tickets.py

# Run pre-flight check
python preflight_check.py
```

### Test Complete Flow

```bash
# 1. Run backlog pipeline
python run_backlog_pipeline.py

# 2. Approve via Telegram

# 3. Verify database
python test_database_update_fix.py

# 4. Run sprint planning
python run_sprint_planning_pipeline.py

# 5. Run standup
python run_standup_pipeline.py
```

## Troubleshooting

### Database Connection Error

```
psycopg2.OperationalError: could not connect to server
```

**Solution:**
- Check PostgreSQL is running
- Verify DATABASE_URL in `.env`
- Test connection: `psql -U postgres -d scrumpilot`

### Missing psycopg2-binary

```
ModuleNotFoundError: No module named 'psycopg2'
```

**Solution:**
```bash
pip install psycopg2-binary
```

### Groq API Error

```
groq.APIError: Invalid API key
```

**Solution:**
- Get API key from https://console.groq.com
- Update GROQ_API_KEY in `.env`

### Jira Authentication Error

```
JIRAError: 401 Unauthorized
```

**Solution:**
- Generate new API token
- Update JIRA_API_TOKEN in `.env`
- Verify JIRA_EMAIL matches your Atlassian account

### Telegram Bot Not Responding

**Solution:**
- Check TELEGRAM_BOT_TOKEN is correct
- Ensure backend is running: `python -m backend.telegram.bot`
- Verify bot is not blocked

## Database Schema

### Core Tables

- **meetings** - Meeting records
- **processing_runs** - Pipeline execution tracking
- **epics** - Epic items with WSJF scores
- **stories** - User stories
- **tasks** - Sub-tasks
- **sprints** - Sprint records
- **sprint_stories** - Sprint-Story mapping
- **scrum_actions** - Standup action items
- **approval_requests** - Approval workflow

## Security

### Environment Variables

Never commit `.env` to Git. The `.gitignore` file excludes:
- `.env` - API keys and secrets
- `.venv/` - Virtual environment
- `*.log` - Log files
- `*.wav`, `*.mp3` - Audio recordings

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/name`
3. Commit changes: `git commit -m 'Add feature'`
4. Push to branch: `git push origin feature/name`
5. Open Pull Request

## License

[Your License Here]

## Support

For issues or questions, open a GitHub issue or check the documentation.

---

**Version**: 1.0.0
