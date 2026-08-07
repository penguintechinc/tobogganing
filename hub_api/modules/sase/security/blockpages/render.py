"""Markdown rendering and HTML sanitization for block pages."""
from __future__ import annotations

import markdown
import bleach
import re

__all__ = ["render_block_page", "VARIABLES"]

# Template variables that can be substituted in block page markdown
VARIABLES = {
    "blocked_url": "The URL that was blocked",
    "category": "The category that triggered the block",
    "reason": "The reason for the block",
    "user": "The user's display name or ID",
    "org": "The organization name",
    "support_link": "Link to support documentation",
    "appeal_link": "Link to submit a block appeal",
    "timestamp": "ISO8601 timestamp of the block",
}

# Allowed HTML tags for sanitized output (defense in depth)
# Markdown can only produce basic safe tags, but we double-check
ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "strong", "em", "b", "i", "u",
    "ul", "ol", "li",
    "a", "img",
    "blockquote", "hr", "pre", "code",
    "div", "span", "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "div": ["class", "id"],
    "span": ["class", "id"],
}


def render_block_page(markdown_text: str, variables: dict[str, str]) -> str:
    """Render markdown block page with variable substitution and HTML sanitization.

    Performs the following steps:
    1. Substitute template variables (e.g., {{blocked_url}})
    2. Convert markdown to HTML
    3. Sanitize the resulting HTML to remove any dangerous tags/attributes
    4. Return the safe HTML

    Args:
        markdown_text: Markdown source with optional template variables.
        variables: Dict mapping variable names (without braces) to values.

    Returns:
        Safe HTML string with variables substituted and markdown converted.

    Example:
        >>> md = "# Blocked\\nURL: {{blocked_url}}"
        >>> html = render_block_page(md, {"blocked_url": "example.com"})
    """
    # Step 1: Substitute variables
    substituted = _substitute_variables(markdown_text, variables)

    # Step 2: Convert markdown to HTML
    html = markdown.markdown(
        substituted,
        extensions=["tables", "fenced_code", "toc"],
        extension_configs={
            "toc": {
                "title": "",
            },
        },
    )

    # Step 3: Sanitize HTML
    safe_html = _sanitize_html(html)

    return safe_html


def _substitute_variables(text: str, variables: dict[str, str]) -> str:
    """Substitute template variables in text.

    Replaces {{variable_name}} with the corresponding value from the
    variables dict. Unknown variables are left as-is.

    Args:
        text: Text containing template variables.
        variables: Dict mapping variable names to values.

    Returns:
        Text with variables substituted.
    """
    def replacer(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))  # Keep original if not found

    # Match {{variable_name}} patterns
    return re.sub(r"\{\{(\w+)\}\}", replacer, text)


def _sanitize_html(html: str) -> str:
    """Sanitize HTML to remove dangerous tags and attributes.

    Uses bleach library for efficient HTML sanitization. This is a defense-in-depth
    measure even though markdown.markdown() only produces safe output from
    trusted input (the admin who authored the page).

    Args:
        html: HTML string to sanitize.

    Returns:
        Sanitized HTML string.
    """
    # Bleach clean function with allowed tags and attributes
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,  # Strip disallowed tags instead of escaping them
    )
