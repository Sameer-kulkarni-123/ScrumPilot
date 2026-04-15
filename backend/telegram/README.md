# ScrumPilot Telegram Bot

Mobile interface for ScrumPilot with Human-in-the-Loop approval workflow.

## Features

### 1. Human-in-the-Loop Approval Workflow ⭐
- PM receives approval requests via Telegram
- Review AI-generated epics/stories on mobile
- Approve, reject, or edit before Jira creation
- Real-time notifications

### 2. Sprint Management
- View current sprint status
- Check assigned tasks
- View team members

### 3. Notifications
- Pending approvals
- Sprint updates
- Task assignments

## Setup

### 1. Get Bot Token

```bash
# 1. Open Telegram
# 2. Search for @BotFather
# 3. Send: /newbot
# 4. Follow instructions
# 5. Save bot token
```

### 2. Configure Environment

```bash
# Add to .env file
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_URL=https://yourdomain.com  # Optional, for production

# Approval settings
APPROVAL_TIMEOUT_HOURS=24
APPROVAL_REMINDER_HOURS=4

# Notification settings
TELEGRAM_NOTIFICATIONS_ENABLED=true
```

### 3. Install Dependencies

```bash
pip install python-telegram-bot[webhooks]
```

### 4. Run Bot

```bash
# Development (polling mode)
python -m backend.telegram.bot

# Production (webhook mode)
# Set TELEGRAM_WEBHOOK_URL in .env first
python -m backend.telegram.bot
```

## Usage

### For PM (Product Owner)

1. **Link Account**
   ```
   /start
   # Send your email when prompted
   ```

2. **View Pending Approvals**
   ```
   /approvals
   # You'll see all pending approval requests
   ```

3. **Approve/Reject**
   - Click ✅ Approve to create in Jira
   - Click ❌ Reject to cancel
   - Click ✏️ Edit to modify before approving
   - Click 👁️ View Details to see full data

### For Developers

1. **Link Account**
   ```
   /start
   ```

2. **Check Your Tasks**
   ```
   /status
   # See all tasks assigned to you
   ```

3. **View Sprint**
   ```
   /sprint
   # See current sprint status
   ```

4. **View Team**
   ```
   /team
   # See all team members
   ```

## Architecture

### Handlers
- `start_handler.py` - Account linking
- `approval_handler.py` - HITL approval workflow
- `callback_handler.py` - Button click handling
- `sprint_handler.py` - Sprint queries
- `help_handler.py` - Help command
- `message_handler.py` - Text message routing

### Services
- `approval_service.py` - Create approval requests

### Integration with Pipelines

```python
# In backlog_pipeline.py
from backend.telegram.services.approval_service import approval_service

# After extracting epics
approval_id = approval_service.create_epic_approval(
    epics_data={'epics': extracted_epics},
    requested_by_user_id=system_user_id,
    assigned_to_user_id=pm_user_id,
    priority='high'
)

# Wait for approval...
# When approved, create in Jira
```

## Approval Workflow

```
PM Meeting
    ↓
Extract Epics (AI)
    ↓
Create Approval Request
    ↓
Send Telegram Notification to PM
    ↓
PM Reviews on Phone
    ↓
[Approve] [Edit] [Reject]
    ↓
If Approved → Create in Jira
If Rejected → Cancel
If Edited → Update data → Create in Jira
```

## Commands

| Command | Description | Who Can Use |
|---------|-------------|-------------|
| `/start` | Link Telegram account | Everyone |
| `/help` | Show help message | Everyone |
| `/approvals` | View pending approvals | PM, Scrum Master |
| `/sprint` | View current sprint | Everyone |
| `/status` | View your tasks | Everyone |
| `/team` | View team members | Everyone |

## Inline Buttons

### Approval Actions
- ✅ **Approve** - Approve and create in Jira
- ❌ **Reject** - Reject and cancel
- ✏️ **Edit** - Modify data before approving
- 👁️ **View Details** - See full approval data

## Database Tables Used

- `users` - User accounts with Telegram fields
- `approval_requests` - Pending approvals
- `approval_history` - Approval audit trail
- `telegram_chat_states` - Conversation tracking
- `telegram_command_history` - Command logging
- `telegram_message_queue` - Message queue
- `telegram_webhook_events` - Webhook logging

## Testing

### Test Account Linking
```bash
# 1. Start bot
python -m backend.telegram.bot

# 2. In Telegram, send:
/start
# Then send your email

# 3. Check database:
SELECT display_name, telegram_user_id, telegram_username 
FROM users 
WHERE telegram_user_id IS NOT NULL;
```

### Test Approval Workflow
```python
# Create test approval
from backend.telegram.services.approval_service import approval_service

approval_id = approval_service.create_epic_approval(
    epics_data={
        'epics': [
            {
                'title': 'Test Epic',
                'description': 'Test description',
                'wsjf': {'wsjf_score': 8.5}
            }
        ]
    },
    requested_by_user_id=1,
    assigned_to_user_id=2,  # PM user ID
    priority='high'
)

# PM should receive Telegram notification
```

## Production Deployment

### Option 1: Polling Mode (Simple)
```bash
# Just run the bot
python -m backend.telegram.bot
```

### Option 2: Webhook Mode (Recommended)
```bash
# 1. Set webhook URL in .env
TELEGRAM_WEBHOOK_URL=https://yourdomain.com

# 2. Run bot
python -m backend.telegram.bot

# 3. Bot will register webhook with Telegram
```

### Option 3: Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "-m", "backend.telegram.bot"]
```

## Troubleshooting

### Bot not responding
```bash
# Check bot token
echo $TELEGRAM_BOT_TOKEN

# Check bot is running
ps aux | grep telegram

# Check logs
tail -f telegram_bot.log
```

### Notifications not sending
```bash
# Check user has Telegram linked
SELECT display_name, telegram_user_id, telegram_notifications_enabled 
FROM users 
WHERE id = YOUR_USER_ID;

# Check message queue
SELECT * FROM telegram_message_queue 
WHERE status = 'pending';
```

### Approval not working
```bash
# Check approval exists
SELECT * FROM approval_requests 
WHERE approval_id = YOUR_APPROVAL_ID;

# Check user has permission
SELECT u.display_name, r.role_name 
FROM users u 
JOIN roles r ON u.role_id = r.role_id 
WHERE u.id = YOUR_USER_ID;
```

## Security

- Bot token stored in environment variable
- User authentication via email linking
- RBAC enforced (only PM can approve)
- All actions logged in database
- Session management with expiry

## Performance

- Async/await for non-blocking operations
- Message queue for rate limiting
- Webhook mode for production (no polling)
- Database connection pooling

## Future Enhancements

- [ ] Edit epic/story data inline
- [ ] Bulk approve/reject
- [ ] Approval reminders
- [ ] Sprint burndown charts
- [ ] Task status updates via Telegram
- [ ] Voice message transcription
- [ ] Group chat support

## Support

For issues or questions:
1. Check logs: `tail -f telegram_bot.log`
2. Check database: `SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 10;`
3. Contact: support@scrumpilot.com
