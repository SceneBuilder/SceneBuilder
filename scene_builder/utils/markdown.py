def wrap_in_code_block(text: str, language: str = "") -> str:
    """
    Wraps the given text in a Markdown code block.

    Args:
        text: The text to wrap.
        language: The language for syntax highlighting.

    Returns:
        The wrapped text.
    """
    return f"```{language}\n{text}\n```"
