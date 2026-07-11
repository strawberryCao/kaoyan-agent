from kaoyan_agent.ui.chat_page import normalize_latex_delimiters


def test_normalize_latex_delimiters_for_streamlit_markdown():
    content = r"\[ \int \sin(2x)\,dx = -\frac12\cos(2x)+C \]"

    normalized = normalize_latex_delimiters(content)

    assert "$$" in normalized
    assert r"\[" not in normalized
    assert r"\]" not in normalized
    assert r"\frac12" in normalized


def test_normalize_latex_delimiters_keeps_code_blocks_unchanged():
    content = "公式：\\(x+1\\)\n```python\nvalue = '\\\\(not math\\\\)'\n```"

    normalized = normalize_latex_delimiters(content)

    assert "公式：$x+1$" in normalized
    assert "value = '\\\\(not math\\\\)'" in normalized
