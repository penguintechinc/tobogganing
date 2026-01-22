"""
Numeric validators - PyDAL-style validators for numeric inputs.

Provides:
- IsInt: Validates integer values
- IsFloat: Validates float values
- IsIntInRange: Validates integer within range
- IsFloatInRange: Validates float within range
- IsPositive: Validates positive numbers
- IsNegative: Validates negative numbers
"""

from __future__ import annotations

from typing import Union

from py_libs.validation.base import ValidationResult, Validator

# Type for numeric inputs that can be converted
NumericInput = Union[int, float, str]


class IsInt(Validator[NumericInput, int]):
    """
    Validates that a value is or can be converted to an integer.

    Example:
        validator = IsInt()
        result = validator(42)      # Valid, returns 42
        result = validator("42")    # Valid, returns 42
        result = validator(3.14)    # Invalid (float)
        result = validator("abc")   # Invalid
    """

    def __init__(self, error_message: str | None = None) -> None:
        self.error_message = error_message or "Value must be an integer"

    def validate(self, value: NumericInput) -> ValidationResult[int]:
        if isinstance(value, bool):  # bool is subclass of int
            return ValidationResult.failure(self.error_message)

        if isinstance(value, int):
            return ValidationResult.success(value)

        if isinstance(value, float):
            if value.is_integer():
                return ValidationResult.success(int(value))
            return ValidationResult.failure(self.error_message)

        if isinstance(value, str):
            try:
                # Don't allow floats in string form
                if "." in value or "e" in value.lower():
                    return ValidationResult.failure(self.error_message)
                return ValidationResult.success(int(value))
            except ValueError:
                return ValidationResult.failure(self.error_message)

        return ValidationResult.failure(self.error_message)


class IsFloat(Validator[NumericInput, float]):
    """
    Validates that a value is or can be converted to a float.

    Example:
        validator = IsFloat()
        result = validator(3.14)    # Valid
        result = validator("3.14")  # Valid
        result = validator(42)      # Valid (int to float)
        result = validator("abc")   # Invalid
    """

    def __init__(self, error_message: str | None = None) -> None:
        self.error_message = error_message or "Value must be a number"

    def validate(self, value: NumericInput) -> ValidationResult[float]:
        if isinstance(value, bool):
            return ValidationResult.failure(self.error_message)

        if isinstance(value, (int, float)):
            return ValidationResult.success(float(value))

        if isinstance(value, str):
            try:
                return ValidationResult.success(float(value))
            except ValueError:
                return ValidationResult.failure(self.error_message)

        return ValidationResult.failure(self.error_message)


class IsIntInRange(Validator[NumericInput, int]):
    """
    Validates that an integer is within a specified range.

    Args:
        min_value: Minimum value (inclusive), or None for no minimum
        max_value: Maximum value (inclusive), or None for no maximum

    Example:
        validator = IsIntInRange(1, 100)
        result = validator(50)   # Valid
        result = validator(0)    # Invalid
        result = validator(101)  # Invalid
    """

    def __init__(
        self,
        min_value: int | None = None,
        max_value: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self.min_value = min_value
        self.max_value = max_value
        self.error_message = error_message

    def validate(self, value: NumericInput) -> ValidationResult[int]:
        # First validate it's an integer
        int_result = IsInt().validate(value)
        if not int_result.is_valid:
            return ValidationResult.failure(
                int_result.error or "Value must be an integer"
            )

        int_value = int_result.value
        assert int_value is not None  # Type narrowing

        if self.min_value is not None and int_value < self.min_value:
            msg = self.error_message or f"Value must be at least {self.min_value}"
            return ValidationResult.failure(msg)

        if self.max_value is not None and int_value > self.max_value:
            msg = self.error_message or f"Value must be at most {self.max_value}"
            return ValidationResult.failure(msg)

        return ValidationResult.success(int_value)


class IsFloatInRange(Validator[NumericInput, float]):
    """
    Validates that a float is within a specified range.

    Args:
        min_value: Minimum value (inclusive), or None for no minimum
        max_value: Maximum value (inclusive), or None for no maximum

    Example:
        validator = IsFloatInRange(0.0, 1.0)
        result = validator(0.5)   # Valid
        result = validator(-0.1)  # Invalid
        result = validator(1.1)   # Invalid
    """

    def __init__(
        self,
        min_value: float | None = None,
        max_value: float | None = None,
        error_message: str | None = None,
    ) -> None:
        self.min_value = min_value
        self.max_value = max_value
        self.error_message = error_message

    def validate(self, value: NumericInput) -> ValidationResult[float]:
        # First validate it's a number
        float_result = IsFloat().validate(value)
        if not float_result.is_valid:
            return ValidationResult.failure(
                float_result.error or "Value must be a number"
            )

        float_value = float_result.value
        assert float_value is not None  # Type narrowing

        if self.min_value is not None and float_value < self.min_value:
            msg = self.error_message or f"Value must be at least {self.min_value}"
            return ValidationResult.failure(msg)

        if self.max_value is not None and float_value > self.max_value:
            msg = self.error_message or f"Value must be at most {self.max_value}"
            return ValidationResult.failure(msg)

        return ValidationResult.success(float_value)


class IsPositive(Validator[NumericInput, float]):
    """
    Validates that a number is positive (> 0).

    Args:
        allow_zero: Whether to allow zero

    Example:
        validator = IsPositive()
        result = validator(5)    # Valid
        result = validator(-5)   # Invalid
        result = validator(0)    # Invalid (unless allow_zero=True)
    """

    def __init__(
        self, allow_zero: bool = False, error_message: str | None = None
    ) -> None:
        self.allow_zero = allow_zero
        self.error_message = error_message

    def validate(self, value: NumericInput) -> ValidationResult[float]:
        float_result = IsFloat().validate(value)
        if not float_result.is_valid:
            return ValidationResult.failure(
                float_result.error or "Value must be a number"
            )

        float_value = float_result.value
        assert float_value is not None

        if self.allow_zero:
            if float_value < 0:
                msg = self.error_message or "Value must be zero or positive"
                return ValidationResult.failure(msg)
        else:
            if float_value <= 0:
                msg = self.error_message or "Value must be positive"
                return ValidationResult.failure(msg)

        return ValidationResult.success(float_value)


class IsNegative(Validator[NumericInput, float]):
    """
    Validates that a number is negative (< 0).

    Args:
        allow_zero: Whether to allow zero

    Example:
        validator = IsNegative()
        result = validator(-5)   # Valid
        result = validator(5)    # Invalid
        result = validator(0)    # Invalid (unless allow_zero=True)
    """

    def __init__(
        self, allow_zero: bool = False, error_message: str | None = None
    ) -> None:
        self.allow_zero = allow_zero
        self.error_message = error_message

    def validate(self, value: NumericInput) -> ValidationResult[float]:
        float_result = IsFloat().validate(value)
        if not float_result.is_valid:
            return ValidationResult.failure(
                float_result.error or "Value must be a number"
            )

        float_value = float_result.value
        assert float_value is not None

        if self.allow_zero:
            if float_value > 0:
                msg = self.error_message or "Value must be zero or negative"
                return ValidationResult.failure(msg)
        else:
            if float_value >= 0:
                msg = self.error_message or "Value must be negative"
                return ValidationResult.failure(msg)

        return ValidationResult.success(float_value)
