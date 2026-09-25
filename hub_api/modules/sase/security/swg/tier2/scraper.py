"""Metadata-only scraper for Tier-2 AI categorizer (Slice E Task 2).

Extracts page metadata using BeautifulSoup:
- Title, meta description
- Headings (h1-h3)
- Bounded visible text
- Strips script/style/hidden elements (injection defense)

Never exposes raw HTML/JS to the classifier.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()

__all__ = ["extract_metadata"]


def extract_metadata(html: bytes, *, max_chars: int = 4000) -> str:
    """Extract metadata from HTML using BeautifulSoup.

    Extracts:
    - Title (<title> tag)
    - Meta description (<meta name="description">)
    - Headings (h1, h2, h3)
    - Bounded visible text (paragraphs, lists, etc.)

    Strips:
    - Script tags (and their content)
    - Style tags (and their content)
    - Hidden elements (display:none)
    - Event handlers

    Args:
        html: HTML content (bytes).
        max_chars: Maximum characters to return (default 4000).

    Returns:
        Extracted metadata as a string, size-capped.
    """
    try:
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style tags (and their content)
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        # Build metadata parts
        parts: list[str] = []

        # Extract title
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            parts.append(title_tag.string.strip())

        # Extract meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            parts.append(meta_desc["content"].strip())

        # Extract h1-h3
        for heading_level in ["h1", "h2", "h3"]:
            for heading in soup.find_all(heading_level):
                heading_text = heading.get_text(strip=True)
                if heading_text:
                    parts.append(heading_text)

        # Extract visible text from body (excluding headings)
        body = soup.find("body")
        if body:
            # Get all text, excluding h1-h3 (already extracted) and hidden elements
            visible_text = _extract_visible_text(body, exclude_headings=True)
            if visible_text:
                parts.append(visible_text)
        else:
            # Fallback: get all text if no body tag
            visible_text = _extract_visible_text(soup, exclude_headings=True)
            if visible_text:
                parts.append(visible_text)

        # Join and cap
        result = " ".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars]

        return result

    except Exception as e:
        logger.warning("extract_metadata_error", error=str(e))
        return ""


def _extract_visible_text(element, *, exclude_headings: bool = False) -> str:
    """Extract visible text from a BeautifulSoup element, skipping hidden content.

    Args:
        element: BeautifulSoup element (tag or root).
        exclude_headings: If True, skip h1-h6 tags (already extracted separately).

    Returns:
        Visible text content.
    """
    text_parts: list[str] = []

    def is_hidden(tag) -> bool:
        """Check if a tag is hidden by CSS."""
        if not hasattr(tag, "get"):
            return False

        style = tag.get("style", "")
        # Check for display:none (with or without spaces)
        if "display:" in style and "none" in style:
            return True

        return False

    def extract_from_tag(tag) -> None:
        """Recursively extract visible text from a tag."""
        # Skip hidden tags
        if is_hidden(tag):
            return

        # Skip script and style (redundant, but safe)
        if tag.name in ["script", "style"]:
            return

        # Skip heading tags if requested
        if exclude_headings and tag.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            return

        # Process children
        for child in tag.children:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    text_parts.append(text)
            else:
                extract_from_tag(child)

    extract_from_tag(element)
    return " ".join(text_parts)
