from kaoyan_agent.core.settings import get_settings
from kaoyan_agent.ui.settings_page import render_settings_page


def render_memories_page() -> None:
    render_settings_page(get_settings())
