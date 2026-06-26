"""URL classification, normalization, and utility functions."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from site_relinker.models import ConfigError


def is_internal(url: str, domains: list[str]) -> bool:
    """Classify a URL as internal or external.

    Handles https://, http://, protocol-relative (//), and root-relative
    (/...) forms.

    Args:
        url: The URL to classify.
        domains: List of domains considered internal.

    Returns:
        True if the URL is internal, False otherwise.
    """
    if url.startswith("/") and not url.startswith("//"):
        return True

    domain = extract_domain(url)
    if domain is None:
        return True

    return domain in domains


def normalize_to_relative(url: str, domains: list[str]) -> str:
    """Strip domain from an internal URL and return a root-relative path.

    Args:
        url: The URL to normalize (absolute or relative).
        domains: List of domains considered internal.

    Returns:
        A root-relative URL path (e.g., "/help/topic.html").

    Raises:
        ValueError: If the URL is external and cannot be normalized.
    """
    if url.startswith("/") and not url.startswith("//"):
        return url

    if not is_internal(url, domains):
        raise ValueError(
            f"Cannot normalize external URL to relative: {url}"
        )

    if url.startswith("//"):
        url = "https:" + url

    parsed = urlparse(url)
    path = parsed.path or "/"
    result = path
    if parsed.query:
        result += "?" + parsed.query
    if parsed.fragment:
        result += "#" + parsed.fragment
    return result


def resolve_relative(base_url: str, href: str) -> str:
    """Resolve a potentially relative href against a base URL.

    Args:
        base_url: The base URL to resolve against.
        href: The href to resolve (absolute or relative).

    Returns:
        The resolved absolute URL.
    """
    if href.startswith(("http://", "https://", "//")):
        return href

    if href.startswith("/"):
        return href

    return urljoin(base_url, href)


def extract_domain(url: str) -> str | None:
    """Return the domain portion of a URL, or None for relative URLs.

    Args:
        url: The URL to extract the domain from.

    Returns:
        The domain string, or None for relative URLs.
    """
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(("http://", "https://")):
        return None

    parsed = urlparse(url)
    return parsed.hostname


def sanitize_classes(classes: list[str]) -> list[str]:
    """Validate CSS class names (alphanumeric + hyphen + underscore).

    Args:
        classes: List of CSS class name strings to validate.

    Returns:
        The validated list of class names.

    Raises:
        ConfigError: If any class name contains invalid characters.
    """
    pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
    for cls in classes:
        if not pattern.match(cls):
            raise ConfigError(
                f"Invalid CSS class name: {cls!r} "
                "(only alphanumeric, hyphens, and underscores allowed)"
            )
    return classes
