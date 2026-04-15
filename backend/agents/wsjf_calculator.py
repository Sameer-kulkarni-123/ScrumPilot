"""
WSJF Calculator Agent

This agent merges data from PM meetings (Business Value) and Sprint Grooming meetings
(Time Criticality, Risk Reduction, Effort) to calculate WSJF scores and prioritize Epics.

WSJF Formula:
    WSJF = (Business Value + Time Criticality + Risk Reduction) / Effort

Author: AI Meeting Automation System
Phase: 3
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class WSJFComponents(BaseModel):
    """WSJF calculation components."""
    business_value: int = Field(..., ge=1, le=10, description="Business Value (1-10)")
    time_criticality: int = Field(..., ge=1, le=10, description="Time Criticality (1-10)")
    risk_reduction: int = Field(..., ge=1, le=10, description="Risk Reduction (1-10)")
    effort: int = Field(..., ge=1, le=10, description="Effort/Job Size (1-10)")


class EpicWithWSJF(BaseModel):
    """Epic with WSJF score and priority."""
    epic_id: str
    title: str
    description: str
    wsjf_components: WSJFComponents
    wsjf_score: float = Field(..., description="Calculated WSJF score")
    priority_rank: int = Field(..., ge=1, description="Priority ranking (1 = highest)")
    mentioned_features: List[str] = Field(default_factory=list)
    confidence: str = "high"


class WSJFData(BaseModel):
    """Complete WSJF calculation data."""
    calculation_date: str
    epics_with_wsjf: List[EpicWithWSJF]
    sorted_by_wsjf: bool = True
    missing_epics: List[Dict] = Field(default_factory=list)
    incomplete_epics: List[Dict] = Field(default_factory=list)


# ============================================================================
# WSJF CALCULATOR AGENT
# ============================================================================

class WSJFCalculatorAgent:
    """
    Agent to calculate WSJF scores by merging PM and Grooming meeting data.
    
    Responsibilities:
    - Load PM meeting data (Business Value)
    - Load Grooming meeting data (Time Criticality, Risk Reduction, Effort)
    - Merge data by epic_id
    - Calculate WSJF scores
    - Rank Epics by WSJF (highest first)
    - Validate data completeness
    - Handle edge cases (division by zero, missing data)
    """

    def __init__(self):
        """Initialize the WSJF Calculator Agent."""
        self.pm_data: Optional[Dict] = None
        self.grooming_data: Optional[Dict] = None
        self.wsjf_data: Optional[WSJFData] = None

    def load_pm_data(self, pm_data_path: str) -> Dict:
        """
        Load PM meeting data from JSON file.

        Args:
            pm_data_path: Path to PM meeting JSON file

        Returns:
            PM meeting data dictionary

        Raises:
            FileNotFoundError: If PM data file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        pm_path = Path(pm_data_path)
        if not pm_path.exists():
            raise FileNotFoundError(
                f"PM meeting data not found: {pm_data_path}\n"
                f"Please run PM meeting extraction first."
            )

        with open(pm_path, 'r', encoding='utf-8') as f:
            self.pm_data = json.load(f)

        print(f"✅ Loaded PM data: {len(self.pm_data.get('epics', []))} Epic(s)")
        return self.pm_data

    def load_grooming_data(self, grooming_data_path: str) -> Dict:
        """
        Load Sprint Grooming meeting data from JSON file.

        Args:
            grooming_data_path: Path to Grooming meeting JSON file

        Returns:
            Grooming meeting data dictionary

        Raises:
            FileNotFoundError: If Grooming data file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        grooming_path = Path(grooming_data_path)
        if not grooming_path.exists():
            raise FileNotFoundError(
                f"Grooming meeting data not found: {grooming_data_path}\n"
                f"Please run Sprint Grooming extraction first."
            )

        with open(grooming_path, 'r', encoding='utf-8') as f:
            self.grooming_data = json.load(f)

        print(f"✅ Loaded Grooming data: {len(self.grooming_data.get('epic_estimates', []))} Epic(s)")
        return self.grooming_data

    def calculate_wsjf(
        self,
        pm_data_path: str,
        grooming_data_path: str,
        allow_incomplete: bool = False
    ) -> WSJFData:
        """
        Calculate WSJF scores by merging PM and Grooming data.

        Args:
            pm_data_path: Path to PM meeting JSON file
            grooming_data_path: Path to Grooming meeting JSON file
            allow_incomplete: If True, calculate WSJF for Epics with complete data only
                            If False, raise error if any Epic is missing estimates

        Returns:
            WSJFData object with calculated scores and priorities

        Raises:
            ValueError: If data is incomplete and allow_incomplete=False
        """
        # Load data
        print("🔍 Loading meeting data...")
        self.load_pm_data(pm_data_path)
        self.load_grooming_data(grooming_data_path)

        # Create Epic lookup from PM data
        pm_epics = {epic['epic_id']: epic for epic in self.pm_data.get('epics', [])}

        # Create Epic lookup from Grooming data
        grooming_estimates = {
            est['epic_id']: est
            for est in self.grooming_data.get('epic_estimates', [])
        }

        # Find missing and incomplete Epics
        missing_epics = []
        incomplete_epics = []
        epics_with_wsjf = []

        print("🧮 Calculating WSJF scores...")

        for epic_id, pm_epic in pm_epics.items():
            # Check if Epic has grooming estimates
            if epic_id not in grooming_estimates:
                missing_epics.append({
                    'epic_id': epic_id,
                    'title': pm_epic['title'],
                    'reason': 'No grooming estimates found'
                })
                continue

            grooming_est = grooming_estimates[epic_id]

            # Validate all components are present
            bv = pm_epic.get('business_value')
            tc = grooming_est.get('time_criticality')
            rr = grooming_est.get('risk_reduction')
            effort = grooming_est.get('effort')

            if None in [bv, tc, rr, effort]:
                incomplete_epics.append({
                    'epic_id': epic_id,
                    'title': pm_epic['title'],
                    'missing_components': [
                        comp for comp, val in [
                            ('business_value', bv),
                            ('time_criticality', tc),
                            ('risk_reduction', rr),
                            ('effort', effort)
                        ] if val is None
                    ]
                })
                continue

            # Handle division by zero
            if effort == 0:
                incomplete_epics.append({
                    'epic_id': epic_id,
                    'title': pm_epic['title'],
                    'reason': 'Effort cannot be zero (division by zero)'
                })
                continue

            # Calculate WSJF and round to 2 decimal places
            wsjf_score = round((bv + tc + rr) / effort, 2)

            # Create Epic with WSJF (temporary rank, will be updated after sorting)
            epic_dict = {
                'epic_id': epic_id,
                'title': pm_epic['title'],
                'description': pm_epic.get('description', ''),
                'wsjf_components': {
                    'business_value': bv,
                    'time_criticality': tc,
                    'risk_reduction': rr,
                    'effort': effort
                },
                'wsjf_score': wsjf_score,
                'mentioned_features': pm_epic.get('mentioned_features', []),
                'confidence': grooming_est.get('confidence', 'high')
            }

            epics_with_wsjf.append(epic_dict)

        # Check for incomplete data
        if (missing_epics or incomplete_epics) and not allow_incomplete:
            error_msg = ["⚠️ WSJF calculation incomplete:\n"]

            if missing_epics:
                error_msg.append(f"Missing grooming estimates for {len(missing_epics)} Epic(s):")
                for epic in missing_epics:
                    error_msg.append(f"  - {epic['title']} ({epic['epic_id']})")

            if incomplete_epics:
                error_msg.append(f"\nIncomplete data for {len(incomplete_epics)} Epic(s):")
                for epic in incomplete_epics:
                    error_msg.append(f"  - {epic['title']} ({epic['epic_id']})")
                    if 'missing_components' in epic:
                        error_msg.append(f"    Missing: {', '.join(epic['missing_components'])}")
                    if 'reason' in epic:
                        error_msg.append(f"    Reason: {epic['reason']}")

            error_msg.append("\nPlease conduct another grooming session or add estimates manually.")
            raise ValueError("\n".join(error_msg))

        # Sort by WSJF score (highest first)
        epics_with_wsjf.sort(key=lambda x: x['wsjf_score'], reverse=True)

        # Assign priority ranks and create Pydantic models
        validated_epics = []
        for rank, epic_dict in enumerate(epics_with_wsjf, start=1):
            epic_dict['priority_rank'] = rank
            validated_epics.append(EpicWithWSJF(**epic_dict))

        # Create WSJF data
        self.wsjf_data = WSJFData(
            calculation_date=datetime.now().strftime('%Y-%m-%d'),
            epics_with_wsjf=validated_epics,
            sorted_by_wsjf=True,
            missing_epics=missing_epics,
            incomplete_epics=incomplete_epics
        )

        print(f"✅ Calculated WSJF for {len(validated_epics)} Epic(s)")

        if missing_epics:
            print(f"⚠️  {len(missing_epics)} Epic(s) missing grooming estimates")

        if incomplete_epics:
            print(f"⚠️  {len(incomplete_epics)} Epic(s) have incomplete data")

        return self.wsjf_data

    def save_wsjf_data(self, output_path: str) -> str:
        """
        Save WSJF data to JSON file.

        Args:
            output_path: Path to save WSJF JSON file

        Returns:
            Path to saved file

        Raises:
            ValueError: If WSJF data hasn't been calculated yet
        """
        if self.wsjf_data is None:
            raise ValueError("No WSJF data to save. Run calculate_wsjf() first.")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict for JSON serialization
        wsjf_dict = self.wsjf_data.model_dump()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(wsjf_dict, f, indent=2, ensure_ascii=False)

        print(f"💾 Saved WSJF data to: {output_file.absolute()}")
        return str(output_file.absolute())

    def get_priority_summary(self) -> str:
        """
        Get a quick summary of Epic priorities.

        Returns:
            Formatted string with Epic priorities

        Raises:
            ValueError: If WSJF data hasn't been calculated yet
        """
        if self.wsjf_data is None:
            raise ValueError("No WSJF data available. Run calculate_wsjf() first.")

        summary = ["WSJF Priority Summary:", "=" * 50]

        for epic in self.wsjf_data.epics_with_wsjf:
            summary.append(
                f"{epic.priority_rank}. {epic.title} - WSJF: {epic.wsjf_score:.2f}"
            )

        return "\n".join(summary)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function for testing."""
    import sys
    from backend.tools.report_generator import ReportGenerator

    # Paths
    pm_data_path = "backend/data/pm_meetings/2026-04-10_extracted_epics.json"
    grooming_data_path = "backend/data/grooming_meetings/2026-04-12_grooming_data.json"
    wsjf_output_path = "backend/data/wsjf/2026-04-12_wsjf_scores.json"
    report_output_path = "backend/data/wsjf/2026-04-12_wsjf_report.md"

    print("=" * 70)
    print("WSJF CALCULATOR AGENT")
    print("=" * 70)

    try:
        # Initialize agent
        agent = WSJFCalculatorAgent()

        # Calculate WSJF
        wsjf_data = agent.calculate_wsjf(
            pm_data_path=pm_data_path,
            grooming_data_path=grooming_data_path,
            allow_incomplete=False
        )

        # Save WSJF data
        agent.save_wsjf_data(wsjf_output_path)

        # Generate report
        print("\n" + "=" * 70)
        print("WSJF REPORT")
        print("=" * 70)
        report = ReportGenerator.generate_wsjf_report(wsjf_data.model_dump())
        print(report)

        # Save report
        report_file = Path(report_output_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n💾 Saved report to: {report_file.absolute()}")

        # Print priority summary
        print("\n" + "=" * 70)
        print("PRIORITY SUMMARY")
        print("=" * 70)
        print(agent.get_priority_summary())

        print("\n🎉 WSJF calculation complete!")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
