"""
GroomingExtractorAgent — Extracts Time Criticality, Risk Reduction, and Effort 
from Sprint Grooming meeting transcripts.

Uses LangChain with Groq LLM to parse grooming discussions and identify:
- Time Criticality (1-10 scale)
- Risk Reduction (1-10 scale)
- Effort/Job Size (1-10 scale)

Implements fuzzy matching to link Epics from PM meeting even when referenced
with different names or abbreviations.

Compatible with langchain==0.1.x / langchain-core==0.1.x
"""

import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from difflib import SequenceMatcher

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser


# ── Structured output schemas ─────────────────────────────────────────────────

class EpicEstimate(BaseModel):
    """Estimates for a single Epic from the grooming meeting."""

    epic_reference: str = Field(
        description="How the Epic was referenced in the grooming meeting (e.g., 'auth system', 'payment gateway')"
    )
    epic_id: Optional[str] = Field(
        default=None,
        description="Matched epic_id from PM meeting (e.g., 'epic_001'). Leave None if no match found."
    )
    epic_title: Optional[str] = Field(
        default=None,
        description="Matched Epic title from PM meeting. Leave None if no match found."
    )
    time_criticality: int = Field(
        description="Time criticality score from 1-10 (10 = most urgent)",
        ge=1,
        le=10
    )
    risk_reduction: int = Field(
        description="Risk reduction score from 1-10 (10 = highest risk reduction)",
        ge=1,
        le=10
    )
    effort: int = Field(
        description="Effort/complexity score from 1-10 (10 = most effort)",
        ge=1,
        le=10
    )
    confidence: Optional[str] = Field(
        default="high",
        description="Confidence level of extraction: 'high', 'medium', or 'low'"
    )


class GroomingEstimates(BaseModel):
    """Complete list of Epic estimates from a grooming meeting."""

    meeting_date: str = Field(
        description="Date of the grooming meeting in YYYY-MM-DD format"
    )
    meeting_type: str = Field(
        default="sprint_grooming",
        description="Type of meeting"
    )
    epic_estimates: List[EpicEstimate] = Field(
        description="All Epic estimates identified in the grooming transcript"
    )


# ── Fuzzy Matching Utility ────────────────────────────────────────────────────

class EpicMatcher:
    """Utility for fuzzy matching Epic references to PM meeting Epics."""

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """
        Calculate similarity ratio between two strings (0.0 to 1.0).
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio (0.0 = no match, 1.0 = exact match)
        """
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text for matching (lowercase, remove common words).
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove common words that don't help matching
        stop_words = ['system', 'the', 'a', 'an', 'integration', 'feature', 'service']
        words = text.split()
        words = [w for w in words if w not in stop_words]
        
        return ' '.join(words)
    
    @staticmethod
    def extract_keywords(text: str) -> set:
        """
        Extract meaningful keywords from text for matching.
        
        Args:
            text: Text to extract keywords from
            
        Returns:
            Set of keywords
        """
        text = text.lower()
        
        # Common abbreviations and their expansions
        abbreviations = {
            'auth': 'authentication',
            'admin': 'administration',
            'notif': 'notification',
            'config': 'configuration',
            'db': 'database',
        }
        
        # Replace abbreviations
        for abbr, full in abbreviations.items():
            if abbr in text:
                text = text.replace(abbr, full)
        
        # Remove stop words
        stop_words = {'system', 'the', 'a', 'an', 'integration', 'feature', 'service', 'thing'}
        words = set(text.split())
        keywords = words - stop_words
        
        return keywords

    @staticmethod
    def find_best_match(
        reference: str,
        pm_epics: List[Dict],
        threshold: float = 0.5
    ) -> Optional[Dict]:
        """
        Find the best matching Epic from PM meeting data.
        
        Uses multiple matching strategies with validation to prevent false positives.
        
        Args:
            reference: How the Epic was referenced in grooming meeting
            pm_epics: List of Epics from PM meeting
            threshold: Minimum similarity score to consider a match (0.0-1.0)
            
        Returns:
            Best matching Epic dict or None if no good match found
        """
        if not pm_epics:
            return None

        normalized_ref = EpicMatcher.normalize_text(reference)
        ref_keywords = EpicMatcher.extract_keywords(reference)
        
        # Require at least one meaningful keyword
        if not ref_keywords:
            return None
        
        best_match = None
        best_score = 0.0

        for epic in pm_epics:
            epic_title = epic.get('title', '')
            
            # Method 1: Direct similarity on full strings
            title_score = EpicMatcher.calculate_similarity(reference, epic_title)
            
            # Method 2: Normalized text similarity
            normalized_title = EpicMatcher.normalize_text(epic_title)
            normalized_score = EpicMatcher.calculate_similarity(normalized_ref, normalized_title)
            
            # Method 3: Word overlap (normalized)
            words_score = 0.0
            ref_words = set(normalized_ref.split())
            title_words = set(normalized_title.split())
            if ref_words and title_words:
                common_words = ref_words.intersection(title_words)
                words_score = len(common_words) / max(len(ref_words), len(title_words))
            
            # Method 4: Keyword matching (with abbreviation expansion)
            title_keywords = EpicMatcher.extract_keywords(epic_title)
            keyword_score = 0.0
            if ref_keywords and title_keywords:
                common_keywords = ref_keywords.intersection(title_keywords)
                keyword_score = len(common_keywords) / max(len(ref_keywords), len(title_keywords))
            
            # Method 5: Substring matching (for partial names)
            substring_score = 0.0
            if len(normalized_ref) >= 4:  # Require at least 4 chars for substring match
                if normalized_ref in normalized_title or normalized_title in normalized_ref:
                    substring_score = 0.7
            
            # Take the best score from all methods
            score = max(title_score, normalized_score, words_score, keyword_score, substring_score)
            
            # Additional validation: require keyword overlap for low direct similarity
            if score < 0.6 and keyword_score == 0:
                # If similarity is low and no keyword overlap, skip this match
                continue
            
            if score > best_score:
                best_score = score
                best_match = epic

        # Only return match if above threshold
        if best_score >= threshold:
            return best_match
        
        return None


# ── Agent class ───────────────────────────────────────────────────────────────

class GroomingExtractorAgent:
    """
    LangChain-powered agent that extracts Time Criticality, Risk Reduction, 
    and Effort from Sprint Grooming meeting transcripts.
    
    Implements fuzzy matching to link Epics from PM meeting.
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        """
        Initialize the GroomingExtractorAgent.

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
        parser = PydanticOutputParser(pydantic_object=GroomingEstimates)
        format_instructions = parser.get_format_instructions()

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are a Sprint Grooming Extractor specialized in analyzing technical "
                    "estimation discussions. Your job is to extract Time Criticality, Risk Reduction, "
                    "and Effort estimates for Epics discussed in grooming meetings.\n\n"
                    "CONTEXT - Epics from PM Meeting:\n{pm_epics_context}\n\n"
                    "EXTRACTION RULES:\n"
                    "1. Epic Reference: Capture how the Epic was mentioned (e.g., 'auth system', 'payment thing')\n"
                    "2. Time Criticality (1-10 scale):\n"
                    "   - If explicitly mentioned, use that exact value\n"
                    "   - If implied from context:\n"
                    "     * 9-10: Critical, urgent, blocking, must-have for launch\n"
                    "     * 7-8: Important, time-sensitive, needed soon\n"
                    "     * 5-6: Moderate urgency, can wait a bit\n"
                    "     * 3-4: Low urgency, nice-to-have\n"
                    "     * 1-2: No urgency, can be delayed\n"
                    "3. Risk Reduction (1-10 scale):\n"
                    "   - If explicitly mentioned, use that exact value\n"
                    "   - If implied:\n"
                    "     * 9-10: Addresses critical security/technical debt/business risks\n"
                    "     * 7-8: Reduces significant risks\n"
                    "     * 5-6: Moderate risk reduction\n"
                    "     * 3-4: Minor risk reduction\n"
                    "     * 1-2: Minimal risk reduction\n"
                    "4. Effort (1-10 scale):\n"
                    "   - If explicitly mentioned, use that exact value\n"
                    "   - If implied from sprint estimates or complexity:\n"
                    "     * 9-10: Very large, complex, many sprints\n"
                    "     * 7-8: Large, significant effort\n"
                    "     * 5-6: Medium effort, a few sprints\n"
                    "     * 3-4: Small effort, 1-2 sprints\n"
                    "     * 1-2: Very small, quick win\n"
                    "5. Confidence: Set to 'high' if values are explicit, 'medium' if inferred, 'low' if unclear\n"
                    "6. DO NOT try to match epic_id or epic_title - leave them as None (matching happens later)\n\n"
                    "IMPORTANT:\n"
                    "- Extract estimates for ALL Epics discussed, even if referenced with different names\n"
                    "- Capture the exact reference used (e.g., 'the auth thing', 'payment gateway')\n"
                    "- If multiple people discuss the same Epic, consolidate into one entry\n"
                    "- Preserve exact values if stated explicitly\n\n"
                    "Output format instructions:\n{format_instructions}"
                ),
            ),
            (
                "human",
                "Here is the Sprint Grooming meeting transcript:\n\n{transcript}\n\n"
                "Extract all Epic estimates with Time Criticality, Risk Reduction, and Effort."
            ),
        ])

        self.chain = prompt | llm | parser
        self._prompt = prompt
        self._parser = parser
        self._format_instructions = format_instructions
        self.matcher = EpicMatcher()

    def extract_estimates(
        self,
        transcript: str,
        pm_epics_data: Dict,
        meeting_date: str = None
    ) -> dict:
        """
        Extract Epic estimates from a grooming transcript and match to PM Epics.

        Args:
            transcript: The full grooming meeting transcript text
            pm_epics_data: Epic data from PM meeting (from Phase 1)
            meeting_date: Optional meeting date (YYYY-MM-DD). If None, uses today's date.

        Returns:
            Dictionary with extracted and matched Epic estimates
        """
        if meeting_date is None:
            meeting_date = datetime.now().strftime("%Y-%m-%d")

        # Prepare PM Epics context for the prompt
        pm_epics = pm_epics_data.get('epics', [])
        pm_epics_context = self._format_pm_epics_context(pm_epics)

        # Extract estimates from transcript
        result: GroomingEstimates = self.chain.invoke({
            "transcript": transcript,
            "pm_epics_context": pm_epics_context,
            "format_instructions": self._format_instructions,
        })

        # Override meeting_date if provided
        result.meeting_date = meeting_date

        # Convert to dict
        result_dict = result.model_dump()

        # Perform fuzzy matching to link estimates to PM Epics
        matched_estimates = []
        for estimate in result_dict['epic_estimates']:
            reference = estimate['epic_reference']
            
            # Find best matching Epic from PM meeting
            matched_epic = self.matcher.find_best_match(reference, pm_epics)
            
            if matched_epic:
                estimate['epic_id'] = matched_epic.get('epic_id')
                estimate['epic_title'] = matched_epic.get('title')
            
            matched_estimates.append(estimate)

        result_dict['epic_estimates'] = matched_estimates

        # Check for missing Epics
        result_dict['missing_epics'] = self._find_missing_epics(
            pm_epics,
            matched_estimates
        )

        return result_dict

    def extract_estimates_from_file(
        self,
        transcript_path: str,
        pm_epics_path: str,
        meeting_date: str = None
    ) -> dict:
        """
        Extract estimates from transcript file and match to PM Epics file.

        Args:
            transcript_path: Path to the grooming transcript text file
            pm_epics_path: Path to the PM meeting Epic data JSON file
            meeting_date: Optional meeting date (YYYY-MM-DD)

        Returns:
            Dictionary with extracted and matched Epic estimates
        """
        # Load transcript
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()

        # Load PM Epics data
        with open(pm_epics_path, "r", encoding="utf-8") as f:
            pm_epics_data = json.load(f)

        # If meeting_date not provided, try to extract from filename
        if meeting_date is None:
            filename = os.path.basename(transcript_path)
            if filename.startswith("20"):
                meeting_date = filename[:10]

        return self.extract_estimates(transcript, pm_epics_data, meeting_date)

    def _format_pm_epics_context(self, pm_epics: List[Dict]) -> str:
        """Format PM Epics for the prompt context."""
        if not pm_epics:
            return "No Epics from PM meeting available."

        lines = []
        for epic in pm_epics:
            epic_id = epic.get('epic_id', 'unknown')
            title = epic.get('title', 'Unknown')
            bv = epic.get('business_value', 0)
            lines.append(f"- {epic_id}: {title} (Business Value: {bv}/10)")

        return "\n".join(lines)

    def _find_missing_epics(
        self,
        pm_epics: List[Dict],
        matched_estimates: List[Dict]
    ) -> List[Dict]:
        """
        Find Epics from PM meeting that weren't discussed in grooming.

        Args:
            pm_epics: List of Epics from PM meeting
            matched_estimates: List of estimates with matched epic_ids

        Returns:
            List of missing Epic dicts
        """
        matched_epic_ids = {
            est.get('epic_id')
            for est in matched_estimates
            if est.get('epic_id')
        }

        missing = []
        for epic in pm_epics:
            epic_id = epic.get('epic_id')
            if epic_id not in matched_epic_ids:
                missing.append({
                    'epic_id': epic_id,
                    'title': epic.get('title'),
                    'business_value': epic.get('business_value')
                })

        return missing


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Example usage
    here = os.path.dirname(__file__)
    
    # Check if example files exist
    grooming_path = os.path.join(
        here, "..", "data", "grooming_meetings", "example_grooming_transcript.txt"
    )
    pm_epics_path = os.path.join(
        here, "..", "data", "pm_meetings", "2026-04-10_extracted_epics.json"
    )
    
    if os.path.exists(grooming_path) and os.path.exists(pm_epics_path):
        print("=" * 60)
        print("GROOMING EXTRACTOR AGENT - Test Run")
        print("=" * 60)
        
        agent = GroomingExtractorAgent()
        result = agent.extract_estimates_from_file(
            grooming_path,
            pm_epics_path,
            meeting_date="2026-04-12"
        )
        
        print(f"\n✅ Extracted {len(result['epic_estimates'])} Epic estimate(s)")
        print(f"⚠️  Missing {len(result.get('missing_epics', []))} Epic(s) from PM meeting\n")
        print(json.dumps(result, indent=2))
    else:
        print(f"Example files not found.")
        print(f"Grooming: {grooming_path}")
        print(f"PM Epics: {pm_epics_path}")
