"""Test SASE block page rendering and sanitization."""
from __future__ import annotations

import pytest

from hub_api.modules.sase.security.blockpages.render import (
    render_block_page,
    VARIABLES,
)


def test_render_heading():
    """Test rendering markdown headings."""
    md = "# Blocked\n## Content Restricted"
    html = render_block_page(md, {})

    assert "<h1" in html
    assert "Blocked" in html
    assert "<h2" in html
    assert "Content Restricted" in html


def test_render_paragraph():
    """Test rendering markdown paragraphs."""
    md = "Your request was blocked.\n\nPlease contact support."
    html = render_block_page(md, {})

    assert "<p>" in html
    assert "Your request was blocked" in html
    assert "contact support" in html


def test_render_list():
    """Test rendering markdown lists."""
    md = "Reasons:\n\n- Malicious content\n- Copyright violation\n- Adult content"
    html = render_block_page(md, {})

    assert "<ul>" in html or "<ol>" in html
    assert "<li>" in html
    assert "Malicious content" in html
    assert "Copyright violation" in html
    assert "Adult content" in html


def test_render_link():
    """Test rendering markdown links."""
    md = "[Contact Support](https://support.example.com)"
    html = render_block_page(md, {})

    assert "<a" in html
    assert "href" in html
    assert "support.example.com" in html
    assert "Contact Support" in html


def test_render_image():
    """Test rendering markdown images."""
    md = "![Logo](https://example.com/logo.png)"
    html = render_block_page(md, {})

    assert "<img" in html
    assert "src" in html
    assert "logo.png" in html


def test_render_strong_emphasis():
    """Test rendering markdown emphasis."""
    md = "This is **bold** and *italic* text."
    html = render_block_page(md, {})

    assert "<strong>" in html or "<b>" in html
    assert "bold" in html
    assert "<em>" in html or "<i>" in html
    assert "italic" in html


def test_substitute_variables():
    """Test variable substitution in markdown."""
    md = "You tried to access {{blocked_url}} which is in the {{category}} category."
    variables = {
        "blocked_url": "example.com",
        "category": "gambling",
    }
    html = render_block_page(md, variables)

    assert "example.com" in html
    assert "gambling" in html


def test_substitute_multiple_vars():
    """Test multiple variable substitutions."""
    md = "User {{user}} from {{org}} tried to access {{blocked_url}}. Reason: {{reason}}"
    variables = {
        "user": "john@example.com",
        "org": "ACME Corp",
        "blocked_url": "gambling-site.com",
        "reason": "gambling",
    }
    html = render_block_page(md, variables)

    assert "john@example.com" in html
    assert "ACME Corp" in html
    assert "gambling-site.com" in html
    assert "gambling" in html


def test_unknown_variable_kept():
    """Test that unknown variables are left as-is."""
    md = "URL: {{blocked_url}} Unknown: {{unknown_var}}"
    html = render_block_page(md, {"blocked_url": "example.com"})

    assert "example.com" in html
    assert "{{unknown_var}}" in html


def test_sanitize_script_tag():
    """Regression: <script> tags in markdown are sanitized out.

    regression: sanitize
    """
    md = "Normal content\n<script>alert('xss')</script>\nMore content"
    html = render_block_page(md, {})

    # Script tag should be removed (no <script> in output)
    assert "<script>" not in html
    # Safe content should remain
    assert "Normal content" in html
    assert "More content" in html
    # The key point: the <script> tag itself is gone, preventing execution


def test_sanitize_style_tag():
    """Regression: <style> tags are sanitized out.

    regression: sanitize
    """
    md = "<style>body { color: red; }</style>\nContent"
    html = render_block_page(md, {})

    # Style tag should be removed
    assert "<style>" not in html
    # Content should remain
    assert "Content" in html
    # The key point: the <style> tag itself is gone, preventing style injection


def test_sanitize_event_handlers():
    """Regression: Event handler attributes are sanitized out.

    regression: sanitize
    """
    md = "<a href='#' onclick='alert(1)'>Click</a>"
    html = render_block_page(md, {})

    # onclick attribute should be removed
    assert "onclick" not in html
    # Link text should remain
    assert "Click" in html


def test_sanitize_javascript_protocol():
    """Regression: JavaScript protocol URLs are sanitized.

    regression: sanitize
    """
    md = "<a href='javascript:alert(1)'>Click</a>"
    html = render_block_page(md, {})

    # The link might be removed or href changed, either is acceptable
    # As long as javascript: is not present
    assert "javascript:" not in html


def test_blockquote():
    """Test rendering markdown blockquotes."""
    md = "> This is a quote\n> from someone"
    html = render_block_page(md, {})

    assert "<blockquote>" in html
    assert "quote" in html


def test_code_block():
    """Test rendering markdown code blocks."""
    md = "```\necho 'hello'\n```"
    html = render_block_page(md, {})

    assert "<pre>" in html or "<code>" in html
    assert "hello" in html


def test_inline_code():
    """Test rendering inline code."""
    md = "Run `command` to proceed"
    html = render_block_page(md, {})

    assert "<code>" in html
    assert "command" in html
    assert "proceed" in html


def test_horizontal_rule():
    """Test rendering horizontal rule."""
    md = "Section 1\n\n---\n\nSection 2"
    html = render_block_page(md, {})

    # Horizontal rule can be <hr> or <hr />
    assert "<hr" in html
    assert "Section 1" in html
    assert "Section 2" in html


def test_complex_page():
    """Test rendering a complete block page."""
    md = """# Access Blocked

Your request to access **{{blocked_url}}** has been blocked.

## Reason
The site is categorized as {{category}}: {{reason}}

## What to do
1. Review our [policies](https://example.com/policies)
2. [Contact support](https://support.example.com) if you believe this is incorrect
3. Submit an [appeal](https://example.com/appeal)

> Last checked: {{timestamp}}

For more information, visit [our help center](https://help.example.com)."""

    variables = {
        "blocked_url": "example-gambling.com",
        "category": "Gambling",
        "reason": "Promotes online gambling",
        "timestamp": "2026-08-06T12:00:00Z",
    }

    html = render_block_page(md, variables)

    # Verify key elements are present
    assert "Access Blocked" in html
    assert "example-gambling.com" in html
    assert "Gambling" in html
    assert "Promotes online gambling" in html
    assert "2026-08-06T12:00:00Z" in html
    assert "policies" in html
    assert "support" in html
    assert "appeal" in html

    # Verify no dangerous tags
    assert "<script>" not in html
    assert "onclick" not in html


def test_variables_dict_exists():
    """Test that VARIABLES dict is properly defined."""
    assert isinstance(VARIABLES, dict)
    assert "blocked_url" in VARIABLES
    assert "category" in VARIABLES
    assert "reason" in VARIABLES
    assert "user" in VARIABLES
    assert "org" in VARIABLES
    assert "support_link" in VARIABLES
    assert "appeal_link" in VARIABLES
    assert "timestamp" in VARIABLES


def test_empty_markdown():
    """Test rendering empty markdown."""
    html = render_block_page("", {})
    assert isinstance(html, str)


def test_only_variables():
    """Test markdown with only variables."""
    md = "{{blocked_url}} {{category}} {{user}}"
    html = render_block_page(md, {
        "blocked_url": "site.com",
        "category": "adult",
        "user": "alice",
    })

    assert "site.com" in html
    assert "adult" in html
    assert "alice" in html


def test_variable_in_link():
    """Test variable substitution inside markdown links."""
    md = "[Report {{blocked_url}}](https://example.com?url={{blocked_url}})"
    html = render_block_page(md, {"blocked_url": "malware-site.com"})

    assert "malware-site.com" in html
    assert "<a" in html
    # The URL part should have substitution too
    assert "malware-site.com" in html
