"""
ScrumExtractorAgent — Uses a LangChain chain (Gemini LLM + PydanticOutputParser)
to parse a diarized meeting transcript into a list of scrum actions.

Compatible with langchain==0.1.x / langchain-core==0.1.x
"""

import os
import json
from typing import List, Optional, Literal

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser


# ── Structured output schemas ─────────────────────────────────────────────────

class ScrumAction(BaseModel):
    """A single scrum action extracted from the meeting transcript."""

    action: Literal[
        "create_task",
        "complete_task",
        "update_status",
        "assign_task",
        "add_comment",
    ] = Field(description="The type of scrum action.")
    summary: str = Field(description="Short title of the task as mentioned in the transcript.")
    description: Optional[str] = Field(
        default=None,
        description="Longer description of the task, only if the speaker provided one.",
    )
    assignee: Optional[str] = Field(
        default=None,
        description="Name of the person responsible, if mentioned.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Target status for update_status actions (e.g. 'In Progress', 'Done').",
    )
    comment: Optional[str] = Field(
        default=None,
        description="The comment text for add_comment actions.",
    )


class ScrumActionList(BaseModel):
    """The complete list of scrum actions extracted from a meeting."""

    actions: List[ScrumAction] = Field(
        description="All actionable scrum items identified in the transcript."
    )


# ── Agent class ───────────────────────────────────────────────────────────────

class ScrumExtractorAgent:
    """LangChain-powered agent that extracts scrum actions from transcripts."""

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
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

        # PydanticOutputParser works with all langchain-core versions
        parser = PydanticOutputParser(pydantic_object=ScrumActionList)
        format_instructions = parser.get_format_instructions()

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are a Scrum Action Extractor. You receive the diarized transcript of a "
                    "scrum / standup meeting and identify every actionable scrum item.\n\n"
                    "Rules:\n"
                    "- 'complete_task' means the speaker said the task is finished / done.\n"
                    "- 'update_status' means moving a task to a specific non-Done status.\n"
                    "- If someone says 'I'll pick up X' or 'I'm working on X', that is "
                    "'update_status' with status 'In Progress'.\n"
                    "- If someone says 'assign X to Y' or 'Y can take X', that is 'assign_task'.\n"
                    "- Only include optional fields when the speaker explicitly mentioned them.\n\n"
                    "Output format instructions:\n{format_instructions}"
                ),
            ),
            ("human", "Here is the diarized meeting transcript:\n\n{transcript}\n\nExtract all scrum actions."),
        ])

        self.chain = prompt | llm | parser
        self._prompt = prompt
        self._parser = parser
        self._format_instructions = format_instructions

    def extract_actions(self, transcript: str) -> List[dict]:
        """
        Send the transcript through the chain and return a list of action dicts.

        Args:
            transcript: The full diarized meeting transcript.

        Returns:
            A list of action dicts (serialized from ScrumAction models).
        """
        result: ScrumActionList = self.chain.invoke({
            "transcript": transcript,
            "format_instructions": self._format_instructions,
        })
        return [action.model_dump(exclude_none=True) for action in result.actions]


# ── Quick standalone test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    here = os.path.dirname(__file__)
    transcript_path = os.path.join(here, "example_transcript.txt")
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    agent = ScrumExtractorAgent()
    actions = agent.extract_actions(transcript)
    print(json.dumps(actions, indent=2))
