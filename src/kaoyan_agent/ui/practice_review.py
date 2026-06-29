from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.mistake_review_page import render_mistake_review_page


def render_practice_review_page(settings: Settings) -> None:
    render_mistake_review_page(settings)
