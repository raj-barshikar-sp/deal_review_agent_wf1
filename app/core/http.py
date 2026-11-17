"""Shared HTTP helpers."""

import ssl


def ssl_context() -> ssl.SSLContext:
    """TLS context that prefers certifi's CA bundle when it is installed."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
