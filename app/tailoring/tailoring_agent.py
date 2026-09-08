"""
Tailoring Agent — produces a tailored CV draft from canonical CV + JD matching report.

Interface: ITailoringAgent.tailor(cv, jd, matching_report, top_projects) -> TailoredCVDraft

Hard constraint (immutable facts rule):
  The agent may ONLY reorder, reweight, or rephrase existing verified data.
  It must NEVER invent experience, skills, metrics, company names, dates, or URLs.
  Enforcement: the underlying facts (company, role, dates, project names/URLs) are
  copied verbatim from the canonical CV. Only ordering and emphasis change.

Pattern mirrors IJDParser and ITriageAgent.
"""
import json
from abc import ABC, abstractmethod
from typing import List
from app.core_schema.models import CV, Project
from app.tailoring.schemas import MatchingReport, TailoredCVDraft


class ITailoringAgent(ABC):
    """Interface for the CV Tailoring Agent."""

    @abstractmethod
    async def tailor(
        self,
        cv: CV,
        matching_report: MatchingReport,
        top_projects: List[Project],
    ) -> TailoredCVDraft:
        pass


class HeuristicTailoringAgent(ITailoringAgent):
    """
    Deterministic tailoring agent for testing and fallback.

    Strategy:
      1. Preserve all underlying facts verbatim (company, role, dates, URLs).
      2. Reorder work_history entries: roles whose description mentions matched JD skills
         are surfaced first.
      3. Select top N projects by relevance score from matching report.
      4. Produce a diff_summary documenting what was reordered.

    No invention of facts. No changes to company names, dates, or descriptions.
    Only the ORDER of work history entries may change.
    """

    async def tailor(
        self,
        cv: CV,
        matching_report: MatchingReport,
        top_projects: List[Project],
    ) -> TailoredCVDraft:
        matched_slugs = {
            m.jd_skill_slug
            for m in matching_report.skill_matches
            if m.match_status in ("matched", "partial")
        }

        # Build canonical work history list (verbatim — no fact changes)
        work_history_raw = []
        if cv.work_histories:
            for wh in cv.work_histories:
                work_history_raw.append({
                    "company": wh.company,          # VERBATIM — never changed
                    "role": wh.role,                # VERBATIM — never changed
                    "location": wh.location,        # VERBATIM — never changed
                    "start_date": wh.start_date,    # VERBATIM — never changed
                    "end_date": wh.end_date,        # VERBATIM — never changed
                    "is_current": wh.is_current,    # VERBATIM — never changed
                    "description": wh.description,  # VERBATIM — only ordering changes
                })

        # Reorder: entries whose description mentions a matched JD skill come first
        def relevance_score(entry: dict) -> int:
            desc = (entry.get("description") or "").lower()
            return sum(1 for slug in matched_slugs if slug in desc)

        reordered = sorted(work_history_raw, key=relevance_score, reverse=True)

        # Build diff summary
        original_order = [e["company"] + " / " + e["role"] for e in work_history_raw]
        new_order = [e["company"] + " / " + e["role"] for e in reordered]
        if original_order != new_order:
            diff_lines = ["Work history reordered to surface most JD-relevant experience first:"]
            for i, (orig, new) in enumerate(zip(original_order, new_order)):
                if orig != new:
                    diff_lines.append(f"  Position {i+1}: was '{orig}', now '{new}'")
            diff_summary = "\n".join(diff_lines)
        else:
            diff_summary = "No reordering needed — current work history order already optimal for this JD."

        selected_ids = [p.id for p in top_projects[:3]]  # Top 3 projects max

        return TailoredCVDraft(
            tailored_summary=cv.summary,  # VERBATIM — not rephrased by heuristic agent
            tailored_work_history=reordered,
            selected_project_ids=selected_ids,
            diff_summary=diff_summary,
        )


class LLMTailoringAgent(ITailoringAgent):
    """
    Stub for LLM-powered tailoring agent (future LangGraph integration).
    The LLM must receive explicit constraints: "Never invent facts. Only reorder and reweight."
    Output validated against TailoredCVDraft before returning.
    """

    async def tailor(
        self,
        cv: CV,
        matching_report: MatchingReport,
        top_projects: List[Project],
    ) -> TailoredCVDraft:
        raise NotImplementedError("LLM tailoring agent client is currently unconfigured.")
