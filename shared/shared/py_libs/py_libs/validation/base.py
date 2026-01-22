"""
Base validation classes and utilities.

Provides the foundation for PyDAL-style validators with:
- Validator abstract base class with __call__ pattern
- ValidationResult dataclass for structured results
- ValidationError exception for validation failures
- chain() function for combining multiple validators
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Generic, Sequence, TypeVar

T = TypeVar("T")
V = TypeVar("V")


class ValidationError(Exception):
    """Exception raised when validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.message = message
        self.field = field
        super().__init__(message)

    def __str__(self) -> str:
        if self.field:
            return f"{self.field}: {self.message}"
        return self.message


@dataclass(slots=True, frozen=True)
class ValidationResult(Generic[T]):
    """
    Result of a validation operation.

    Attributes:
        is_valid: Whether the validation passed
        value: The validated (possibly transformed) value, or None if invalid
        error: Error message if validation failed, or None if valid
    """

    is_valid: bool
    value: T | None
    error: str | None

    @classmethod
    def success(cls, value: T) -> ValidationResult[T]:
        """Create a successful validation result."""
        return cls(is_valid=True, value=value, error=None)

    @classmethod
    def failure(cls, error: str) -> ValidationResult[Any]:
        """Create a failed validation result."""
        return cls(is_valid=False, value=None, error=error)

    def unwrap(self) -> T:
        """
        Get the validated value or raise ValidationError.

        Returns:
            The validated value

        Raises:
            ValidationError: If validation failed
        """
        if not self.is_valid or self.value is None:
            raise ValidationError(self.error or "Validation failed")
        return self.value

    def unwrap_or(self, default: T) -> T:
        """
        Get the validated value or return a default.

        Args:
            default: Value to return if validation failed

        Returns:
            The validated value or the default
        """
        if self.is_valid and self.value is not None:
            return self.value
        return default


class Validator(ABC, Generic[T, V]):
    """
    Abstract base class for validators.

    Validators follow the PyDAL IS_* pattern with __call__ method.
    Subclasses must implement the validate() method.

    Type Parameters:
        T: Input type
        V: Output type (may be transformed)

    Example:
        class IsUpper(Validator[str, str]):
            def validate(self, value: str) -> ValidationResult[str]:
                if value.isupper():
                    return ValidationResult.success(value)
                return ValidationResult.failure("Value must be uppercase")

        validator = IsUpper()
        result = validator("HELLO")  # ValidationResult(is_valid=True, value="HELLO")
    """

    def __call__(self, value: T) -> ValidationResult[V]:
        """
        Validate the input value.

        Args:
            value: The value to validate

        Returns:
            ValidationResult with success/failure status
        """
        return self.validate(value)

    @abstractmethod
    def validate(self, value: T) -> ValidationResult[V]:
        """
        Perform the actual validation.

        Args:
            value: The value to validate

        Returns:
            ValidationResult with success/failure status
        """
        ...

    def and_then(self, other: Validator[V, Any]) -> ChainedValidator[T, Any]:
        """
        Chain this validator with another.

        Args:
            other: The next validator in the chain

        Returns:
            A new ChainedValidator that runs both validators
        """
        return ChainedValidator([self, other])


class ChainedValidator(Validator[T, V]):
    """
    A validator that chains multiple validators together.

    Validators are run in sequence. If any validator fails,
    the chain stops and returns the failure result.
    """

    def __init__(self, validators: Sequence[Validator[Any, Any]]) -> None:
        self._validators = list(validators)

    def validate(self, value: T) -> ValidationResult[V]:
        """Run all validators in sequence."""
        current_value: Any = value

        for validator in self._validators:
            result = validator(current_value)
            if not result.is_valid:
                return ValidationResult.failure(result.error or "Validation failed")
            current_value = result.value

        return ValidationResult.success(current_value)

    def and_then(self, other: Validator[V, Any]) -> ChainedValidator[T, Any]:
        """Add another validator to the chain."""
        return ChainedValidator([*self._validators, other])


def chain(*validators: Validator[Any, Any]) -> ChainedValidator[Any, Any]:
    """
    Create a chained validator from multiple validators.

    Validators are run in sequence. If any validator fails,
    the chain stops and returns the failure result.

    Args:
        *validators: Validators to chain together

    Returns:
        A ChainedValidator that runs all validators in order

    Example:
        validators = chain(IsNotEmpty(), IsLength(3, 50), IsEmail())
        result = validators("user@example.com")
    """
    return ChainedValidator(validators)


# Type alias for validator functions
ValidatorFunc = Callable[[Any], ValidationResult[Any]]
