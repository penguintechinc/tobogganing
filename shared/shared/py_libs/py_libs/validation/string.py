"""
String validators - PyDAL-style validators for string inputs.

Provides:
- IsNotEmpty: Validates non-empty strings
- IsLength: Validates string length range
- IsMatch: Validates against regex pattern
- IsAlphanumeric: Validates alphanumeric characters only
- IsSlug: Validates URL-safe slug format
- IsIn: Validates value is in allowed set
- IsTrimmed: Validates and trims whitespace
"""

from __future__ import annotations

import re
from typing import Pattern, Sequence

from py_libs.validation.base import ValidationResult, Validator


class IsNotEmpty(Validator[str, str]):
    """
    Validates that a string is not empty or whitespace-only.

    Example:
        validator = IsNotEmpty()
        result = validator("hello")  # Valid
        result = validator("")       # Invalid
        result = validator("   ")    # Invalid
    """

    def __init__(self, error_message: str | None = None) -> None:
        self.error_message = error_message or "Value cannot be empty"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        stripped = value.strip()
        if not stripped:
            return ValidationResult.failure(self.error_message)

        return ValidationResult.success(stripped)


class IsLength(Validator[str, str]):
    """
    Validates that a string length is within a range.

    Args:
        min_length: Minimum length (inclusive), default 0
        max_length: Maximum length (inclusive), default None (unlimited)

    Example:
        validator = IsLength(3, 50)
        result = validator("hello")  # Valid
        result = validator("hi")     # Invalid (too short)
    """

    def __init__(
        self,
        min_length: int = 0,
        max_length: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self.min_length = min_length
        self.max_length = max_length
        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        length = len(value)

        if length < self.min_length:
            msg = (
                self.error_message
                or f"Value must be at least {self.min_length} characters"
            )
            return ValidationResult.failure(msg)

        if self.max_length is not None and length > self.max_length:
            msg = (
                self.error_message
                or f"Value must be at most {self.max_length} characters"
            )
            return ValidationResult.failure(msg)

        return ValidationResult.success(value)


class IsMatch(Validator[str, str]):
    """
    Validates that a string matches a regex pattern.

    Args:
        pattern: Regex pattern (string or compiled Pattern)
        flags: Regex flags (only used if pattern is a string)

    Example:
        validator = IsMatch(r"^[A-Z]{2}\\d{4}$")
        result = validator("AB1234")  # Valid
        result = validator("abc123")  # Invalid
    """

    def __init__(
        self,
        pattern: str | Pattern[str],
        flags: int = 0,
        error_message: str | None = None,
    ) -> None:
        if isinstance(pattern, str):
            self._pattern = re.compile(pattern, flags)
        else:
            self._pattern = pattern
        self.error_message = error_message or "Value does not match required pattern"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        if not self._pattern.match(value):
            return ValidationResult.failure(self.error_message)

        return ValidationResult.success(value)


class IsAlphanumeric(Validator[str, str]):
    """
    Validates that a string contains only alphanumeric characters.

    Args:
        allow_underscore: Whether to allow underscores
        allow_dash: Whether to allow dashes

    Example:
        validator = IsAlphanumeric()
        result = validator("Hello123")  # Valid
        result = validator("Hello!")    # Invalid
    """

    def __init__(
        self,
        allow_underscore: bool = False,
        allow_dash: bool = False,
        error_message: str | None = None,
    ) -> None:
        self.allow_underscore = allow_underscore
        self.allow_dash = allow_dash
        self.error_message = error_message

        # Build pattern based on options
        chars = "a-zA-Z0-9"
        if allow_underscore:
            chars += "_"
        if allow_dash:
            chars += "-"
        self._pattern = re.compile(f"^[{chars}]+$")

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        if not value:
            return ValidationResult.failure("Value cannot be empty")

        if not self._pattern.match(value):
            msg = (
                self.error_message or "Value must contain only alphanumeric characters"
            )
            return ValidationResult.failure(msg)

        return ValidationResult.success(value)


class IsSlug(Validator[str, str]):
    """
    Validates that a string is a valid URL slug.

    A valid slug contains only lowercase letters, numbers, and hyphens,
    starts and ends with alphanumeric, and has no consecutive hyphens.

    Example:
        validator = IsSlug()
        result = validator("my-blog-post")    # Valid
        result = validator("My Blog Post")    # Invalid
        result = validator("--invalid--")     # Invalid
    """

    _SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def __init__(self, error_message: str | None = None) -> None:
        self.error_message = error_message or "Value must be a valid URL slug"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        if not value:
            return ValidationResult.failure("Value cannot be empty")

        if not self._SLUG_PATTERN.match(value):
            return ValidationResult.failure(self.error_message)

        return ValidationResult.success(value)


class IsIn(Validator[str, str]):
    """
    Validates that a value is in an allowed set.

    Args:
        options: Allowed values
        case_sensitive: Whether comparison is case-sensitive

    Example:
        validator = IsIn(["admin", "user", "guest"])
        result = validator("admin")   # Valid
        result = validator("Admin")   # Invalid (case-sensitive)

        validator = IsIn(["admin", "user"], case_sensitive=False)
        result = validator("ADMIN")   # Valid
    """

    def __init__(
        self,
        options: Sequence[str],
        case_sensitive: bool = True,
        error_message: str | None = None,
    ) -> None:
        self.case_sensitive = case_sensitive
        if case_sensitive:
            self._options = set(options)
        else:
            self._options = {o.lower() for o in options}
        self._original_options = list(options)
        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        check_value = value if self.case_sensitive else value.lower()

        if check_value not in self._options:
            msg = (
                self.error_message
                or f"Value must be one of: {', '.join(self._original_options)}"
            )
            return ValidationResult.failure(msg)

        return ValidationResult.success(value)


class IsTrimmed(Validator[str, str]):
    """
    Validates and trims whitespace from a string.

    This validator always succeeds (for non-empty values) and returns
    the trimmed string.

    Example:
        validator = IsTrimmed()
        result = validator("  hello  ")  # Returns "hello"
    """

    def __init__(self, allow_empty: bool = False) -> None:
        self.allow_empty = allow_empty

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        trimmed = value.strip()

        if not trimmed and not self.allow_empty:
            return ValidationResult.failure("Value cannot be empty")

        return ValidationResult.success(trimmed)
