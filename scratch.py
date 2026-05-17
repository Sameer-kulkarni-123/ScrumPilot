import re

with open('backend/agents/jira_creator.py', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(r'# Create each Epic with its Stories and Tasks.*?# ── Live-Jira guard:', re.DOTALL)
replacement = """# Resolve project routing ONCE for the entire backlog to ensure a flattened hierarchy
        overall_project_key = None
        if epics_data:
            first_epic = epics_data[0]
            global_routing = self.resolve_routing(first_epic.get('title', ''), first_epic.get('description', ''))
            overall_project_key = global_routing.project_key
            logger.info(f"Globally resolved project key for backlog: {overall_project_key}")

        # Create each Epic with its Stories and Tasks
        for epic_data in epics_data:
            epic_id = epic_data.get('epic_id', '')
            epic_title = epic_data.get('title', '')
            epic_description_text = epic_data.get('description', '')

            if dry_run:
                print(
                    f"  [DRY RUN] Would create Epic: {epic_title} "
                    f"→ project={overall_project_key}"
                )
                continue

            # Inherit global project routing for the entire flat backlog
            epic_project_key = overall_project_key
            epic_component = None

            # ── Live-Jira guard:"""

new_content = pattern.sub(replacement, content)

with open('backend/agents/jira_creator.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Replaced!")
