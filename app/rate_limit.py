"""
Single shared Limiter instance (slowapi, built on the `limits` library).
Keyed by client IP. Kept in its own module so both main.py (for wiring)
and individual routers (for the @limiter.limit(...) decorator) can
import it without a circular import.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import DEFAULT_RATE_LIMIT

limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_RATE_LIMIT])
