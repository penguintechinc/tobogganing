"""
py_libs - Shared Python libraries for secure application development.

This package provides "batteries included" security-focused utilities:
- validation: PyDAL-style input validators
- security: Rate limiting, CSRF, secure headers, sanitization
- crypto: Token generation, hashing, encryption
- http: Request correlation, resilient HTTP client
- grpc: gRPC server/client with security interceptors
"""

__version__ = "1.0.0"
__author__ = "Penguin Tech Inc"
__email__ = "dev@penguintech.io"

from py_libs.validation import (
    ValidationResult,
    Validator,
    chain,
)

__all__ = [
    "__version__",
    "ValidationResult",
    "Validator",
    "chain",
]
