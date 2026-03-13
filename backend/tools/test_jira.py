import os
from dotenv import load_dotenv
from jira_client import JiraManager

# Load environment variables from .env file
# By default, it looks for .env in the current working directory.
load_dotenv()

def run_jira_diagnostic():
    print("🚀 Starting Jira Connection Diagnostic...")
    
    # Pre-check environment variables to give better error messages
    required_vars = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"\n❌ ERROR: Missing variables in .env: {', '.join(missing)}")
        print(f"Current Working Directory: {os.getcwd()}")
        print("Please ensure your .env file is in the root of the project or the directory you are running this from.")
        return

    try:
        # 1. Initialize the Manager
        print("\n[1/4] Initializing JiraManager...")
        manager = JiraManager()
        print("✅ Initialization successful.")

        # 2. Test Connection by fetching project info
        print("\n[2/4] Verifying connection and project key...")
        project = manager.client.project(manager.project_key)
        print(f"✅ Connected to Project: {project.name} ({project.key})")

        # 3. Create a Test Ticket
        print("\n[3/4] Attempting to create a test ticket...")
        summary = "🧪 Automated Test Ticket"
        description = "This ticket was created by the ScrumPilot diagnostic script to verify API permissions."
        result = manager.create_ticket(summary, description)
        print(f"✅ {result}")
        
        # Extract the key for the next steps
        new_ticket_key = result.split(": ")[1]

        # 4. Add a comment to the new ticket
        print(f"\n[4/4] Adding a comment to {new_ticket_key}...")
        manager.add_comment(new_ticket_key, "Connection test successful! The bot can now comment on issues.")
        print("✅ Comment added successfully.")

        print("\n" + "="*30)
        print("🎉 DIAGNOSTIC COMPLETE: ALL SYSTEMS GO!")
        print("Check your Jira board to see the 'Automated Test Ticket'.")
        print("="*30)

    except Exception as e:
        print("\n❌ DIAGNOSTIC FAILED")
        print(f"Error Type: {type(e).__name__}")
        print(f"Details: {str(e)}")
        print("\nTroubleshooting Tips:")
        print("1. Check if JIRA_API_TOKEN is correct.")
        print("2. Ensure JIRA_URL includes 'https://' and ends with '.net'.")
        print("3. Verify that your JIRA_EMAIL has 'Admin' or 'Write' permissions on the project.")

if __name__ == "__main__":
    run_jira_diagnostic()