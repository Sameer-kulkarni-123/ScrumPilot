"""
ReportGenerator — Utility class for generating human-readable reports from agent outputs.

Generates Markdown reports for:
- PM meeting Epic extraction
- Sprint grooming estimates
- WSJF calculations
- Jira creation results
"""

import os
from typing import Dict, List
from datetime import datetime


class ReportGenerator:
    """Utility class for generating human-readable reports."""

    @staticmethod
    def generate_pm_report(epics_data: Dict) -> str:
        """
        Generate a human-readable report from PM meeting Epic extraction.

        Args:
            epics_data: Dictionary containing extracted Epics (from BacklogExtractorAgent)

        Returns:
            Markdown-formatted report string
        """
        meeting_date = epics_data.get("meeting_date", "Unknown")
        epics = epics_data.get("epics", [])

        report = []
        report.append("# PM MEETING REPORT")
        report.append("=" * 70)
        report.append(f"**Meeting Date**: {meeting_date}")
        report.append(f"**Meeting Type**: PM-Stakeholder")
        report.append(f"**Epics Extracted**: {len(epics)}")
        report.append("")
        report.append("---")
        report.append("")

        if not epics:
            report.append("⚠️ No Epics were extracted from this meeting.")
            report.append("")
            return "\n".join(report)

        report.append("## EXTRACTED EPICS")
        report.append("")

        for i, epic in enumerate(epics, 1):
            epic_id = epic.get("epic_id", "unknown")
            title = epic.get("title", "Untitled Epic")
            description = epic.get("description", "No description")
            business_value = epic.get("business_value", 0)
            features = epic.get("mentioned_features", [])
            confidence = epic.get("confidence", "unknown")

            # Business value bar visualization
            bv_bar = "█" * business_value + "░" * (10 - business_value)

            report.append(f"### {i}. {title}")
            report.append(f"**Epic ID**: `{epic_id}`")
            report.append(f"**Business Value**: {business_value}/10 [{bv_bar}]")
            report.append(f"**Confidence**: {confidence.upper()}")
            report.append("")
            report.append(f"**Description**:")
            report.append(f"{description}")
            report.append("")

            if features:
                report.append(f"**Mentioned Features**:")
                for feature in features:
                    report.append(f"- {feature}")
                report.append("")

            report.append("---")
            report.append("")

        # Add review instructions
        report.append("## REVIEW INSTRUCTIONS")
        report.append("")
        report.append("Please review the extracted Epics for accuracy:")
        report.append("")
        report.append("1. ✅ Verify Epic titles are clear and accurate")
        report.append("2. ✅ Check Business Value scores (1-10)")
        report.append("3. ✅ Confirm descriptions capture the Epic scope")
        report.append("4. ✅ Review mentioned features list")
        report.append("")
        report.append("**If corrections are needed**:")
        report.append(f"- Edit the JSON file: `backend/data/pm_meetings/{meeting_date}_extracted_epics.json`")
        report.append("- Update Epic titles, descriptions, or business values as needed")
        report.append("- Proceed to Sprint Grooming meeting once approved")
        report.append("")
        report.append("---")
        report.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    @staticmethod
    def generate_grooming_report(grooming_data: Dict, pm_epics_data: Dict = None) -> str:
        """
        Generate a human-readable report from Sprint Grooming extraction.

        Args:
            grooming_data: Dictionary containing grooming estimates
            pm_epics_data: Optional PM meeting data for context

        Returns:
            Markdown-formatted report string
        """
        meeting_date = grooming_data.get("meeting_date", "Unknown")
        epic_estimates = grooming_data.get("epic_estimates", [])
        missing_epics = grooming_data.get("missing_epics", [])

        # Build PM Epics lookup map for context
        pm_epics_map = {}
        if pm_epics_data:
            for epic in pm_epics_data.get('epics', []):
                pm_epics_map[epic.get('epic_id')] = epic

        report = []
        report.append("# SPRINT GROOMING REPORT")
        report.append("=" * 70)
        report.append(f"**Meeting Date**: {meeting_date}")
        report.append(f"**Meeting Type**: Sprint Grooming")
        report.append(f"**Epics Estimated**: {len(epic_estimates)}")
        
        if missing_epics:
            report.append(f"**⚠️ Missing Epics**: {len(missing_epics)}")
        
        report.append("")
        report.append("---")
        report.append("")

        if not epic_estimates:
            report.append("⚠️ No Epic estimates were extracted from this meeting.")
            report.append("")
            return "\n".join(report)

        report.append("## EPIC ESTIMATES")
        report.append("")

        for i, estimate in enumerate(epic_estimates, 1):
            epic_id = estimate.get("epic_id", "unknown")
            epic_title = estimate.get("epic_title", "Unknown Epic")
            epic_reference = estimate.get("epic_reference", "")
            tc = estimate.get("time_criticality", 0)
            rr = estimate.get("risk_reduction", 0)
            effort = estimate.get("effort", 0)

            # Visualization bars
            tc_bar = "█" * tc + "░" * (10 - tc)
            rr_bar = "█" * rr + "░" * (10 - rr)
            effort_bar = "█" * effort + "░" * (10 - effort)

            report.append(f"### {i}. {epic_title}")
            report.append(f"**Epic ID**: `{epic_id}`")
            
            # Add PM meeting context if available
            if epic_id in pm_epics_map:
                pm_epic = pm_epics_map[epic_id]
                bv = pm_epic.get('business_value', 0)
                bv_bar = "█" * bv + "░" * (10 - bv)
                report.append(f"**Business Value**: {bv}/10 [{bv_bar}] *(from PM meeting)*")
                report.append("")
                
                # Show Epic description from PM meeting
                description = pm_epic.get('description', '')
                if description:
                    report.append(f"**Epic Description**:")
                    report.append(f"{description}")
                    report.append("")
                
                # Show mentioned features from PM meeting
                features = pm_epic.get('mentioned_features', [])
                if features:
                    report.append(f"**Mentioned Features** *(from PM meeting)*:")
                    for feature in features[:5]:  # Show first 5 features
                        report.append(f"- {feature}")
                    if len(features) > 5:
                        report.append(f"- *...and {len(features) - 5} more*")
                    report.append("")
            
            report.append(f"**Sprint Grooming Estimates**:")
            if epic_reference:
                report.append(f"*(Referenced as: \"{epic_reference}\")*")
            report.append("")
            report.append(f"**Time Criticality**: {tc}/10 [{tc_bar}]")
            report.append(f"**Risk Reduction**: {rr}/10 [{rr_bar}]")
            report.append(f"**Effort**: {effort}/10 [{effort_bar}]")
            report.append("")
            report.append("---")
            report.append("")

        # Add missing Epics warning section
        if missing_epics:
            report.append("## ⚠️ MISSING EPICS")
            report.append("")
            report.append("The following Epics from the PM meeting were **NOT discussed** in this grooming session:")
            report.append("")
            
            for epic in missing_epics:
                epic_id = epic.get('epic_id', 'unknown')
                title = epic.get('title', 'Unknown')
                bv = epic.get('business_value', 0)
                bv_bar = "█" * bv + "░" * (10 - bv)
                
                report.append(f"### ❌ {title}")
                report.append(f"**Epic ID**: `{epic_id}`")
                report.append(f"**Business Value**: {bv}/10 [{bv_bar}]")
                report.append("")
                report.append("**Status**: ⚠️ **Needs estimation in another grooming session**")
                report.append("")
            
            report.append("---")
            report.append("")
            report.append("**⚠️ ACTION REQUIRED**: Schedule another grooming session to estimate the missing Epics above.")
            report.append("")
            report.append("---")
            report.append("")

        # Add review instructions
        report.append("## REVIEW INSTRUCTIONS")
        report.append("")
        report.append("Please review the extracted estimates:")
        report.append("")
        report.append("1. ✅ Verify Time Criticality scores (1-10)")
        report.append("2. ✅ Check Risk Reduction scores (1-10)")
        report.append("3. ✅ Confirm Effort estimates (1-10)")
        report.append("4. ✅ Ensure all Epics from PM meeting are covered")
        
        if missing_epics:
            report.append("5. ⚠️ **Schedule grooming for missing Epics**")
        
        report.append("")
        report.append("**If corrections are needed**:")
        report.append(f"- Edit the JSON file: `backend/data/grooming_meetings/{meeting_date}_grooming_data.json`")
        report.append("- Proceed to WSJF calculation once approved")
        report.append("")
        report.append("---")
        report.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    @staticmethod
    def generate_wsjf_report(wsjf_data: Dict) -> str:
        """
        Generate a human-readable WSJF calculation report.

        Args:
            wsjf_data: Dictionary containing WSJF scores and priorities

        Returns:
            Markdown-formatted report string
        """
        calc_date = wsjf_data.get("calculation_date", "Unknown")
        epics = wsjf_data.get("epics_with_wsjf", [])

        report = []
        report.append("# WSJF CALCULATION REPORT")
        report.append("=" * 70)
        report.append(f"**Calculation Date**: {calc_date}")
        report.append(f"**Total Epics**: {len(epics)}")
        report.append("")
        report.append("**WSJF Formula**: (Business Value + Time Criticality + Risk Reduction) / Effort")
        report.append("")
        report.append("---")
        report.append("")

        if not epics:
            report.append("⚠️ No Epics available for WSJF calculation.")
            report.append("")
            return "\n".join(report)

        report.append("## PRIORITIZED BACKLOG (by WSJF Score)")
        report.append("")

        for epic in epics:
            rank = epic.get("priority_rank", 0)
            title = epic.get("title", "Unknown Epic")
            wsjf_score = epic.get("wsjf_score", 0.0)
            components = epic.get("wsjf_components", {})

            bv = components.get("business_value", 0)
            tc = components.get("time_criticality", 0)
            rr = components.get("risk_reduction", 0)
            effort = components.get("effort", 0)

            # Priority indicator
            if rank == 1:
                priority_icon = "🥇 HIGHEST PRIORITY"
            elif rank == 2:
                priority_icon = "🥈 HIGH PRIORITY"
            elif rank == 3:
                priority_icon = "🥉 MEDIUM PRIORITY"
            else:
                priority_icon = f"#{rank}"

            report.append(f"### {rank}. {title} - WSJF: {wsjf_score:.2f} {priority_icon}")
            report.append("")
            report.append("**WSJF Components**:")
            report.append(f"- Business Value: {bv}/10")
            report.append(f"- Time Criticality: {tc}/10")
            report.append(f"- Risk Reduction: {rr}/10")
            report.append(f"- Effort: {effort}/10")
            report.append("")
            report.append(f"**Calculation**: ({bv} + {tc} + {rr}) / {effort} = {wsjf_score:.2f}")
            report.append("")
            report.append("---")
            report.append("")

        # Add missing Epics warning section
        missing_epics = wsjf_data.get("missing_epics", [])
        incomplete_epics = wsjf_data.get("incomplete_epics", [])

        if missing_epics:
            report.append("## ⚠️ MISSING EPICS")
            report.append("")
            report.append("The following Epics from PM meeting were not estimated in grooming:")
            report.append("")
            for epic in missing_epics:
                report.append(f"- **{epic['title']}** (`{epic['epic_id']}`)")
                report.append(f"  - Reason: {epic.get('reason', 'No grooming estimates found')}")
                report.append("")
            report.append("**Action Required**: Schedule grooming session for these Epics")
            report.append("")
            report.append("---")
            report.append("")

        if incomplete_epics:
            report.append("## ⚠️ INCOMPLETE EPICS")
            report.append("")
            report.append("The following Epics have incomplete data:")
            report.append("")
            for epic in incomplete_epics:
                report.append(f"- **{epic['title']}** (`{epic['epic_id']}`)")
                if 'missing_components' in epic:
                    report.append(f"  - Missing: {', '.join(epic['missing_components'])}")
                if 'reason' in epic:
                    report.append(f"  - Reason: {epic['reason']}")
                report.append("")
            report.append("**Action Required**: Complete grooming estimates for these Epics")
            report.append("")
            report.append("---")
            report.append("")

        # Add review instructions
        report.append("## REVIEW INSTRUCTIONS")
        report.append("")
        report.append("Please review the WSJF scores and priorities:")
        report.append("")
        report.append("1. ✅ Verify WSJF calculations are correct")
        report.append("2. ✅ Confirm priority ranking makes business sense")
        report.append("3. ✅ Check if any manual adjustments are needed")
        
        if missing_epics or incomplete_epics:
            report.append("4. ⚠️ **Address missing/incomplete Epics before proceeding**")
        
        report.append("")
        report.append("**If corrections are needed**:")
        report.append(f"- Edit the JSON file: `backend/data/wsjf/{calc_date}_wsjf_scores.json`")
        report.append("- Adjust WSJF components or scores as needed")
        report.append("- Proceed to Epic decomposition once approved")
        report.append("")
        report.append("---")
        report.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    @staticmethod
    def generate_decomposition_report(decomposed_data: Dict) -> str:
        """
        Generate a human-readable decomposition report from Epic decomposition data.

        Includes decomposition date, total counts, per-Epic breakdown with Stories,
        Acceptance Criteria, Sub-tasks with hour estimates, and summary statistics.

        Args:
            decomposed_data: Dictionary from DecomposedBacklog.model_dump()

        Returns:
            Markdown-formatted report string
        """
        decomp_date = decomposed_data.get("decomposition_date", "Unknown")
        total_epics = decomposed_data.get("total_epics", 0)
        total_stories = decomposed_data.get("total_stories", 0)
        total_tasks = decomposed_data.get("total_tasks", 0)
        total_hours = decomposed_data.get("total_estimated_hours", 0)
        epics = decomposed_data.get("epics", [])

        report = []
        report.append("# EPIC DECOMPOSITION REPORT")
        report.append("=" * 70)
        report.append(f"**Decomposition Date**: {decomp_date}")
        report.append(f"**Total Epics**: {total_epics}")
        report.append(f"**Total User Stories**: {total_stories}")
        report.append(f"**Total Sub-tasks**: {total_tasks}")
        report.append(f"**Total Estimated Hours**: {total_hours}h")
        report.append("")
        report.append("---")
        report.append("")

        if not epics:
            report.append("⚠️ No Epics were decomposed.")
            report.append("")
            return "\n".join(report)

        report.append("## DECOMPOSED BACKLOG (by WSJF Priority)")
        report.append("")

        for epic in epics:
            rank = epic.get("priority_rank", 0)
            title = epic.get("title", "Unknown Epic")
            wsjf_score = epic.get("wsjf_score", 0.0)
            description = epic.get("description", "")
            stories = epic.get("stories", [])

            # Priority indicator
            if rank == 1:
                priority_icon = "🥇 HIGHEST PRIORITY"
            elif rank == 2:
                priority_icon = "🥈 HIGH PRIORITY"
            elif rank == 3:
                priority_icon = "🥉 MEDIUM PRIORITY"
            else:
                priority_icon = f"#{rank}"

            # Calculate Epic totals
            epic_tasks = sum(len(s.get("tasks", [])) for s in stories)
            epic_hours = sum(
                t.get("estimated_hours", 0)
                for s in stories
                for t in s.get("tasks", [])
            )

            report.append(f"### {rank}. {title} — WSJF: {wsjf_score:.2f} {priority_icon}")
            report.append(f"**Epic ID**: `{epic.get('epic_id', 'unknown')}`")
            report.append(f"**Description**: {description}")
            report.append(f"**Stories**: {len(stories)} | **Sub-tasks**: {epic_tasks} | "
                          f"**Estimated Hours**: {epic_hours}h")
            report.append("")

            # Stories
            for s_idx, story in enumerate(stories, 1):
                story_id = story.get("story_id", f"story_{s_idx:03d}")
                story_title = story.get("title", "Untitled Story")
                story_desc = story.get("description", "")
                criteria = story.get("acceptance_criteria", [])
                tasks = story.get("tasks", [])

                story_hours = sum(t.get("estimated_hours", 0) for t in tasks)

                report.append(f"#### Story {s_idx}: {story_title}")
                report.append(f"**Story ID**: `{story_id}` | **Sub-tasks**: {len(tasks)} | "
                              f"**Hours**: {story_hours}h")
                report.append("")

                if story_desc:
                    report.append(f"**Description**: {story_desc}")
                    report.append("")

                # Acceptance Criteria
                if criteria:
                    report.append("**Acceptance Criteria**:")
                    for c_idx, criterion in enumerate(criteria, 1):
                        report.append(f"  {c_idx}. ✅ {criterion}")
                    report.append("")

                # Sub-tasks table
                if tasks:
                    report.append("**Sub-tasks**:")
                    report.append("")
                    report.append("| Task ID | Title | Hours |")
                    report.append("|---------|-------|-------|")
                    for task in tasks:
                        task_id = task.get("task_id", "")
                        task_title = task.get("title", "")
                        task_hours = task.get("estimated_hours", 0)
                        hours_bar = "█" * (task_hours // 2) + "░" * ((16 - task_hours) // 2)
                        report.append(f"| `{task_id}` | {task_title} | {task_hours}h {hours_bar} |")
                    report.append("")

            report.append("---")
            report.append("")

        # Summary Statistics
        report.append("## 📊 SUMMARY STATISTICS")
        report.append("")
        report.append("| Metric | Value |")
        report.append("|--------|-------|")
        report.append(f"| Total Epics | {total_epics} |")
        report.append(f"| Total User Stories | {total_stories} |")
        report.append(f"| Total Sub-tasks | {total_tasks} |")
        report.append(f"| Total Estimated Hours | {total_hours}h |")

        if total_epics > 0:
            avg_stories = total_stories / total_epics
            report.append(f"| Avg Stories per Epic | {avg_stories:.1f} |")

        if total_stories > 0:
            avg_tasks = total_tasks / total_stories
            avg_hours = total_hours / total_stories
            report.append(f"| Avg Sub-tasks per Story | {avg_tasks:.1f} |")
            report.append(f"| Avg Hours per Story | {avg_hours:.1f}h |")

        report.append("")

        # Effort distribution by Epic
        report.append("## ⏱️ EFFORT DISTRIBUTION BY EPIC")
        report.append("")

        for epic in epics:
            epic_hours = sum(
                t.get("estimated_hours", 0)
                for s in epic.get("stories", [])
                for t in s.get("tasks", [])
            )
            if total_hours > 0:
                percentage = (epic_hours / total_hours) * 100
            else:
                percentage = 0

            bar_len = int(percentage / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            report.append(f"- **{epic.get('title', 'Unknown')}**: {epic_hours}h ({percentage:.0f}%) [{bar}]")

        report.append("")

        # Review instructions
        report.append("## REVIEW INSTRUCTIONS")
        report.append("")
        report.append("Please review the decomposed backlog:")
        report.append("")
        report.append("1. ✅ Verify User Stories cover Epic scope completely")
        report.append("2. ✅ Check Story titles follow 'As a [user]...' format")
        report.append("3. ✅ Confirm Acceptance Criteria are testable and specific")
        report.append("4. ✅ Review Sub-task hour estimates (4-16h each)")
        report.append("5. ✅ Ensure Stories are independently deliverable")
        report.append("6. ✅ Verify total effort is realistic for your team")
        report.append("")
        report.append("**If corrections are needed**:")
        report.append(f"- Edit the JSON file: `backend/data/decomposed/{decomp_date}_decomposed_backlog.json`")
        report.append("- Adjust Stories, Sub-tasks, or hour estimates as needed")
        report.append("- Proceed to Jira creation once approved")
        report.append("")
        report.append("---")
        report.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    @staticmethod
    def generate_jira_report(jira_results: Dict) -> str:
        """
        Generate a human-readable Jira creation report.

        Args:
            jira_results: Dictionary containing Jira creation results from JiraCreatorAgent

        Returns:
            Markdown-formatted report string
        """
        creation_date = jira_results.get("creation_date", "Unknown")
        total_epics = jira_results.get("total_epics", 0)
        total_stories = jira_results.get("total_stories", 0)
        total_tasks = jira_results.get("total_tasks", 0)
        epics_created = jira_results.get("epics_created", 0)
        stories_created = jira_results.get("stories_created", 0)
        tasks_created = jira_results.get("tasks_created", 0)
        epics = jira_results.get("epics", [])
        errors = jira_results.get("errors", [])

        report = []
        report.append("# JIRA CREATION REPORT")
        report.append("=" * 70)
        report.append(f"**Creation Date**: {creation_date}")
        report.append(f"**Epics Created**: {epics_created}/{total_epics}")
        report.append(f"**Stories Created**: {stories_created}/{total_stories}")
        report.append(f"**Sub-tasks Created**: {tasks_created}/{total_tasks}")
        report.append("")

        # Success rate
        success_rate = 0
        if total_epics > 0:
            total_items = total_epics + total_stories + total_tasks
            created_items = epics_created + stories_created + tasks_created
            success_rate = (created_items / total_items) * 100 if total_items > 0 else 0
            report.append(f"**Success Rate**: {success_rate:.1f}%")
            report.append("")

        if errors:
            report.append(f"⚠️ **Errors Encountered**: {len(errors)}")
        else:
            report.append("✅ **All items created successfully**")

        report.append("")
        report.append("---")
        report.append("")

        # Epic details
        for epic_data in epics:
            epic_key = epic_data.get("jira_key", "FAILED")
            epic_title = epic_data.get("title", "Unknown")
            wsjf_score = epic_data.get("wsjf_score", 0.0)
            priority_rank = epic_data.get("priority_rank", 0)
            epic_success = epic_data.get("success", False)
            stories = epic_data.get("stories", [])

            # Epic header with status
            status_icon = "✅" if epic_success else "❌"
            report.append(f"## {status_icon} EPIC: {epic_title}")
            if epic_success:
                report.append(f"**Jira Key**: {epic_key}")
            report.append(f"**WSJF Score**: {wsjf_score:.2f} | **Priority**: #{priority_rank}")
            
            if not epic_success:
                error = epic_data.get("error", "Unknown error")
                report.append(f"**Error**: {error}")
            
            report.append("")

            # Stories
            if stories:
                for story_data in stories:
                    story_key = story_data.get("jira_key", "FAILED")
                    story_title = story_data.get("title", "Unknown")
                    story_points = story_data.get("story_points")
                    story_success = story_data.get("success", False)
                    tasks = story_data.get("tasks", [])

                    status_icon = "  ✅" if story_success else "  ❌"
                    report.append(f"### {status_icon} Story: {story_title[:80]}...")
                    if story_success:
                        report.append(f"**Jira Key**: {story_key}")
                    if story_points:
                        report.append(f"**Story Points**: {story_points}")
                    
                    if not story_success:
                        error = story_data.get("error", "Unknown error")
                        report.append(f"**Error**: {error}")
                    
                    report.append("")

                    # Sub-tasks
                    if tasks:
                        report.append("**Sub-tasks**:")
                        for task in tasks:
                            task_key = task.get("jira_key", "FAILED")
                            task_title = task.get("title", "Unknown")
                            task_hours = task.get("estimated_hours", 0)
                            task_points = task.get("story_points")
                            task_success = task.get("success", False)

                            status_icon = "✅" if task_success else "❌"
                            task_info = f"{task_title[:60]}"
                            if task_success:
                                task_info += f" ({task_key})"
                            task_info += f" - {task_hours}h"
                            if task_points:
                                task_info += f", {task_points} pts"
                            
                            report.append(f"- {status_icon} {task_info}")
                        report.append("")

            report.append("---")
            report.append("")

        # Errors section
        if errors:
            report.append("## ⚠️ ERRORS")
            report.append("")
            for i, error in enumerate(errors, 1):
                report.append(f"{i}. {error}")
            report.append("")
            report.append("---")
            report.append("")

        # Summary
        report.append("## 📊 SUMMARY")
        report.append("")
        report.append(f"✅ Successfully created {epics_created} Epics, {stories_created} Stories, {tasks_created} Sub-tasks")
        
        if epics_created < total_epics or stories_created < total_stories or tasks_created < total_tasks:
            failed_epics = total_epics - epics_created
            failed_stories = total_stories - stories_created
            failed_tasks = total_tasks - tasks_created
            report.append(f"❌ Failed to create {failed_epics} Epics, {failed_stories} Stories, {failed_tasks} Sub-tasks")
        
        report.append("")
        
        # Link to Jira
        if epics and epics[0].get("success"):
            first_epic_key = epics[0].get("jira_key", "")
            if first_epic_key:
                # Extract project key (e.g., "SP" from "SP-100")
                project_key = first_epic_key.split("-")[0] if "-" in first_epic_key else ""
                # Use actual Jira URL from environment or default
                jira_url = os.getenv("JIRA_URL", "https://your-jira.atlassian.net")
                report.append(f"**View in Jira**: {jira_url}/browse/{first_epic_key}")
                report.append(f"**Project Board**: {jira_url}/jira/software/projects/{project_key}/board")
                report.append("")

        report.append("---")
        report.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Example usage
    example_epics = {
        "meeting_date": "2026-04-10",
        "meeting_type": "pm_stakeholder",
        "epics": [
            {
                "epic_id": "epic_001",
                "title": "User Authentication System",
                "description": "Complete authentication system with login, signup, and OAuth",
                "business_value": 9,
                "mentioned_features": ["Login", "Signup", "Password reset", "OAuth"],
                "confidence": "high"
            },
            {
                "epic_id": "epic_002",
                "title": "Payment Gateway Integration",
                "description": "Integrate Stripe for payment processing",
                "business_value": 10,
                "mentioned_features": ["Stripe integration", "Payment UI", "Webhooks"],
                "confidence": "high"
            }
        ]
    }

    print("=" * 70)
    print("REPORT GENERATOR - Test Run")
    print("=" * 70)
    print()

    report = ReportGenerator.generate_pm_report(example_epics)
    print(report)
