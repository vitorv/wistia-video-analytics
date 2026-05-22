"""Typed exceptions for the ingestion pipeline.

The client translates low-level ``requests`` failures into these so callers can
react by failure mode — e.g. abort on an auth failure, skip a single bad media
on a 404, abort on a transient API error.
"""


class WistiaError(Exception):
    """Base class for all ingestion-pipeline errors."""


class WistiaAuthError(WistiaError):
    """Authentication failed (HTTP 401) — typically a bad or missing API token."""


class WistiaNotFoundError(WistiaError):
    """Requested resource does not exist (HTTP 404) — e.g. an unknown media ID."""


class WistiaAPIError(WistiaError):
    """Any other API failure — a non-401/404 HTTP status, or a connection error."""
