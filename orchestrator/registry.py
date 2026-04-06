from functools import lru_cache
from orchestrator.orchestrator import Orchestrator
from agents.research_agent import ResearchAgent
from agents.executor_agent import ExecutorAgent
from agents.profile_intelligence_agent import ProfileIntelligenceAgent
from agents.competitor_analysis_agent import CompetitorAnalysisAgent
from agents.calendar_agent import CalendarAgent
from agents.copy_agent import CopyAgent
from agents.hashtag_agent import HashtagAgent
from agents.visual_agent import VisualAgent


@lru_cache
def get_orchestrator() -> Orchestrator:
    orch = Orchestrator()
    orch.register(ResearchAgent())
    orch.register(ExecutorAgent())
    orch.register(ProfileIntelligenceAgent())
    orch.register(CompetitorAnalysisAgent())
    orch.register(CalendarAgent())
    orch.register(CopyAgent())
    orch.register(HashtagAgent())
    orch.register(VisualAgent())
    return orch
