"""
BacklogExtractorAgent — Extracts Epics and Business Value from PM-Stakeholder meeting transcripts.

Uses LangChain with Groq LLM to parse meeting discussions and identify:
- Epic titles
- Epic descriptions
- Business Value (1-10 scale)
- Mentioned features/requirements

Compatible with langchain==0.1.x / langchain-core==0.1.x
"""

import os
import json
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser


# ── Structured output schemas ─────────────────────────────────────────────────

class Epic(BaseModel):
    """A single Epic extracted from the PM meeting transcript."""

    epic_id: str = Field(
        description="Unique identifier for the Epic (e.g., 'epic_001', 'epic_002')"
    )
    title: str = Field(
        description="Short, clear title of the Epic (e.g., 'User Authentication System')"
    )
    description: str = Field(
        description="Detailed description of what the Epic entails"
    )
    business_value: int = Field(
        description="Business value score from 1-10 (10 = highest value)",
        ge=1,
        le=10
    )
    mentioned_features: List[str] = Field(
        description="List of specific features or requirements mentioned for this Epic"
    )
    confidence: Optional[str] = Field(
        default="high",
        description="Confidence level of extraction: 'high', 'medium', or 'low'"
    )


class EpicList(BaseModel):
    """Complete list of Epics extracted from a PM meeting."""

    meeting_date: str = Field(
        description="Date of the meeting in YYYY-MM-DD format"
    )
    meeting_type: str = Field(
        default="pm_stakeholder",
        description="Type of meeting"
    )
    epics: List[Epic] = Field(
        description="All Epics identified in the meeting transcript"
    )


# ── Agent class ───────────────────────────────────────────────────────────────

class BacklogExtractorAgent:
    """
    LangChain-powered agent that extracts Epics and Business Value from 
    PM-Stakeholder meeting transcripts.
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        """
        Initialize the BacklogExtractorAgent.

        Args:
            model_name: Groq model to use for extraction
        """
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )

        llm = ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=0,
        )

        # PydanticOutputParser for structured output
        parser = PydanticOutputParser(pydantic_object=EpicList)
        format_instructions = parser.get_format_instructions()

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are a Product Backlog Extractor specialized in analyzing PM-Stakeholder "
                    "meeting transcripts. Your job is to identify Epics (large features/projects) "
                    "and extract their Business Value.\n\n"
                    "EXTRACTION RULES:\n"
                    "1. Epic Title: Create a clear, concise title (e.g., 'User Authentication System')\n"
                    "2. Epic Description: Summarize what the Epic entails based on discussion\n"
                    "3. Business Value (1-10 scale):\n"
                    "   - If explicitly mentioned (e.g., 'business value is 9'), use that exact value\n"
                    "   - If implied from context (e.g., 'critical for revenue', 'must-have'), infer the value:\n"
                    "     * 9-10: Critical, must-have, high revenue impact, strategic importance\n"
                    "     * 7-8: Important, significant value, competitive advantage\n"
                    "     * 5-6: Moderate value, nice-to-have, incremental improvement\n"
                    "     * 3-4: Low value, minor impact\n"
                    "     * 1-2: Minimal value, optional\n"
                    "4. Mentioned Features: List all specific features/requirements discussed\n"
                    "5. Confidence: Set to 'high' if values are explicit, 'medium' if inferred, 'low' if unclear\n"
                    "6. Epic ID: Generate sequential IDs (epic_001, epic_002, etc.)\n\n"
                    "IMPORTANT:\n"
                    "- Only extract items that are clearly new features/projects (Epics)\n"
                    "- Don't extract minor tasks or bug fixes\n"
                    "- If multiple people discuss the same Epic, consolidate into one entry\n"
                    "- Preserve the exact Business Value if stated explicitly\n\n"
                    "Output format instructions:\n{format_instructions}"
                ),
            ),
            (
                "human",
                "Here is the PM-Stakeholder meeting transcript:\n\n{transcript}\n\n"
                "Extract all Epics with their Business Value."
            ),
        ])

        self.chain = prompt | llm | parser
        self._prompt = prompt
        self._parser = parser
        self._format_instructions = format_instructions

    def extract_epics(self, transcript: str, meeting_date: str = None) -> dict:
        """
        Extract Epics and Business Value from a meeting transcript.

        Args:
            transcript: The full PM meeting transcript text
            meeting_date: Optional meeting date (YYYY-MM-DD). If None, uses today's date.

        Returns:
            Dictionary with extracted Epic data
        """
        if meeting_date is None:
            meeting_date = datetime.now().strftime("%Y-%m-%d")

        result: EpicList = self.chain.invoke({
            "transcript": transcript,
            "format_instructions": self._format_instructions,
        })

        # Override meeting_date if provided
        result.meeting_date = meeting_date

        # Convert to dict for JSON serialization
        return result.model_dump()

    def extract_epics_from_file(self, transcript_path: str, meeting_date: str = None) -> dict:
        """
        Extract Epics from a transcript file.

        Args:
            transcript_path: Path to the transcript text file
            meeting_date: Optional meeting date (YYYY-MM-DD)

        Returns:
            Dictionary with extracted Epic data
        """
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()

        # If meeting_date not provided, try to extract from filename
        if meeting_date is None:
            filename = os.path.basename(transcript_path)
            # Try to extract date from filename like "2026-04-10_pm_transcript.txt"
            if filename.startswith("20"):
                meeting_date = filename[:10]

        return self.extract_epics(transcript, meeting_date)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Example usage
    here = os.path.dirname(__file__)
    
    # Check if example transcript exists
    example_path = os.path.join(here, "..", "data", "pm_meetings", "example_pm_transcript.txt")
    
    if os.path.exists(example_path):
        print("=" * 60)
        print("BACKLOG EXTRACTOR AGENT - Test Run")
        print("=" * 60)
        
        agent = BacklogExtractorAgent()
        result = agent.extract_epics_from_file(example_path)
        
        print(f"\n✅ Extracted {len(result['epics'])} Epic(s):\n")
        print(json.dumps(result, indent=2))
    else:
        print(f"Example transcript not found at: {example_path}")
        print("Create an example transcript to test the agent.")
