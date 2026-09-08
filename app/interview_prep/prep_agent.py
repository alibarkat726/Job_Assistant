from abc import ABC, abstractmethod
from typing import List

from app.core_schema.models import Project
from app.tailoring.schemas import StructuredJDRequirement, SkillMatchResult
from app.interview_prep.schemas import StructuredInterviewPrepSet, StructuredInterviewQuestion


class IInterviewPrepAgent(ABC):
    """
    Interface for the Interview Prep Generation Agent.
    Any concrete implementation (e.g. Heuristic, LangGraph) must satisfy this.
    """
    @abstractmethod
    async def generate(
        self, 
        jd_requirements: List[StructuredJDRequirement], 
        matched_skills: List[SkillMatchResult], 
        projects: List[Project]
    ) -> StructuredInterviewPrepSet:
        pass


class HeuristicInterviewPrepAgent(IInterviewPrepAgent):
    """
    A heuristic implementation of the Interview Prep Agent.
    Simulates generation by looking at the matched skills and ranked projects.
    Ensures all generated questions are strictly grounded in the real data.
    """

    async def generate(
        self, 
        jd_requirements: List[StructuredJDRequirement], 
        matched_skills: List[SkillMatchResult], 
        projects: List[Project]
    ) -> StructuredInterviewPrepSet:
        questions = []
        
        # 1. Technical / Skill-based questions
        for match in matched_skills:
            if match.match_status == "matched":
                questions.append(StructuredInterviewQuestion(
                    question_text=f"How have you applied {match.jd_skill_name} in your previous work?",
                    category="technical",
                    rationale=f"JD requires {match.jd_skill_name}; your CV shows you have this skill.",
                    suggested_answer_outline=f"Discuss a specific challenge you solved using {match.jd_skill_name}."
                ))
            elif match.match_status == "missing" and match.is_required:
                questions.append(StructuredInterviewQuestion(
                    question_text=f"The role requires {match.jd_skill_name}, but it's not explicitly on your CV. How would you quickly ramp up on this?",
                    category="technical",
                    rationale=f"JD requires {match.jd_skill_name} but it is missing from your profile.",
                    suggested_answer_outline="Acknowledge the gap and mention a related skill you can transfer from, or your plan to learn it."
                ))

        # 2. Project-based questions
        for proj in projects:
            skill_names = [ps.skill.name for ps in proj.project_skills]
            skills_str = ", ".join(skill_names) if skill_names else "various technologies"
            questions.append(StructuredInterviewQuestion(
                question_text=f"Walk me through the architecture and your specific contributions to {proj.title}.",
                category="project",
                rationale=f"Based on your shortlisted project '{proj.title}' which demonstrates {skills_str}.",
                suggested_answer_outline="Focus on your specific impact, the trade-offs you considered, and how it aligns with this job's needs."
            ))

        # 3. Behavioral question
        # Generate at least one standard behavioral question tailored to seniority if present
        seniority = next((req.seniority for req in jd_requirements if req.seniority), None)
        if seniority == "senior":
            q_text = "Tell me about a time you had to mentor a junior engineer or lead a complex technical decision."
            q_rat = "JD implies a senior role; leadership and mentoring are often evaluated."
        else:
            q_text = "Tell me about a time you had to overcome a difficult technical blocker."
            q_rat = "Standard behavioral question to evaluate problem-solving and resilience."

        questions.append(StructuredInterviewQuestion(
            question_text=q_text,
            category="behavioral",
            rationale=q_rat,
            suggested_answer_outline="Use the STAR method: Situation, Task, Action, Result."
        ))

        return StructuredInterviewPrepSet(questions=questions)
