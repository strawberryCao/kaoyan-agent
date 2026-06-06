from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.task_page import render_task_page


def render_planning_page(settings: Settings) -> None:
    render_task_page(settings)
