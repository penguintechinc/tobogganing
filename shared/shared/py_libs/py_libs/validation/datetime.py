"""
DateTime validators - PyDAL-style validators for date/time inputs.

Provides:
- IsDate: Validates date strings
- IsDateTime: Validates datetime strings
- IsTime: Validates time strings
- IsDateInRange: Validates date is within range
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Union

from py_libs.validation.base import ValidationResult, Validator

# Type for date/time inputs
DateInput = Union[str, date, datetime]
TimeInput = Union[str, time, datetime]
DateTimeInput = Union[str, datetime]


class IsDate(Validator[DateInput, date]):
    """
    Validates that a value is or can be parsed as a date.

    Args:
        format: Expected date format (strptime format string)
                Default: "%Y-%m-%d" (ISO 8601)

    Example:
        validator = IsDate()
        result = validator("2024-01-15")  # Valid
        result = validator("15/01/2024")  # Invalid (wrong format)

        validator = IsDate(format="%d/%m/%Y")
        result = validator("15/01/2024")  # Valid
    """

    def __init__(
        self, format: str = "%Y-%m-%d", error_message: str | None = None
    ) -> None:
        self.format = format
        self.error_message = error_message

    def validate(self, value: DateInput) -> ValidationResult[date]:
        if isinstance(value, datetime):
            return ValidationResult.success(value.date())

        if isinstance(value, date):
            return ValidationResult.success(value)

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return ValidationResult.failure(self._get_error_message())

            try:
                parsed = datetime.strptime(value, self.format)
                return ValidationResult.success(parsed.date())
            except ValueError:
                return ValidationResult.failure(self._get_error_message())

        return ValidationResult.failure("Value must be a string or date")

    def _get_error_message(self) -> str:
        return self.error_message or f"Invalid date format. Expected: {self.format}"


class IsDateTime(Validator[DateTimeInput, datetime]):
    """
    Validates that a value is or can be parsed as a datetime.

    Args:
        format: Expected datetime format (strptime format string)
                Default: "%Y-%m-%dT%H:%M:%S" (ISO 8601)

    Example:
        validator = IsDateTime()
        result = validator("2024-01-15T14:30:00")  # Valid
        result = validator("2024-01-15")           # Invalid (missing time)

        validator = IsDateTime(format="%Y-%m-%d %H:%M")
        result = validator("2024-01-15 14:30")     # Valid
    """

    def __init__(
        self,
        format: str = "%Y-%m-%dT%H:%M:%S",
        error_message: str | None = None,
    ) -> None:
        self.format = format
        self.error_message = error_message

    def validate(self, value: DateTimeInput) -> ValidationResult[datetime]:
        if isinstance(value, datetime):
            return ValidationResult.success(value)

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return ValidationResult.failure(self._get_error_message())

            try:
                parsed = datetime.strptime(value, self.format)
                return ValidationResult.success(parsed)
            except ValueError:
                return ValidationResult.failure(self._get_error_message())

        return ValidationResult.failure("Value must be a string or datetime")

    def _get_error_message(self) -> str:
        return self.error_message or f"Invalid datetime format. Expected: {self.format}"


class IsTime(Validator[TimeInput, time]):
    """
    Validates that a value is or can be parsed as a time.

    Args:
        format: Expected time format (strptime format string)
                Default: "%H:%M:%S"

    Example:
        validator = IsTime()
        result = validator("14:30:00")  # Valid
        result = validator("14:30")     # Invalid (missing seconds)

        validator = IsTime(format="%H:%M")
        result = validator("14:30")     # Valid
    """

    def __init__(
        self, format: str = "%H:%M:%S", error_message: str | None = None
    ) -> None:
        self.format = format
        self.error_message = error_message

    def validate(self, value: TimeInput) -> ValidationResult[time]:
        if isinstance(value, datetime):
            return ValidationResult.success(value.time())

        if isinstance(value, time):
            return ValidationResult.success(value)

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return ValidationResult.failure(self._get_error_message())

            try:
                parsed = datetime.strptime(value, self.format)
                return ValidationResult.success(parsed.time())
            except ValueError:
                return ValidationResult.failure(self._get_error_message())

        return ValidationResult.failure("Value must be a string or time")

    def _get_error_message(self) -> str:
        return self.error_message or f"Invalid time format. Expected: {self.format}"


class IsDateInRange(Validator[DateInput, date]):
    """
    Validates that a date is within a specified range.

    Args:
        min_date: Minimum date (inclusive), or None for no minimum
        max_date: Maximum date (inclusive), or None for no maximum
        format: Date format for parsing strings

    Example:
        from datetime import date

        validator = IsDateInRange(
            min_date=date(2024, 1, 1),
            max_date=date(2024, 12, 31)
        )
        result = validator("2024-06-15")  # Valid
        result = validator("2023-12-31")  # Invalid (before min)
    """

    def __init__(
        self,
        min_date: date | None = None,
        max_date: date | None = None,
        format: str = "%Y-%m-%d",
        error_message: str | None = None,
    ) -> None:
        self.min_date = min_date
        self.max_date = max_date
        self.format = format
        self.error_message = error_message

    def validate(self, value: DateInput) -> ValidationResult[date]:
        # First parse the date
        date_validator = IsDate(format=self.format)
        result = date_validator.validate(value)
        if not result.is_valid:
            return ValidationResult.failure(result.error or "Invalid date")

        date_value = result.value
        assert date_value is not None  # Type narrowing

        # Check range
        if self.min_date is not None and date_value < self.min_date:
            msg = self.error_message or f"Date must be on or after {self.min_date}"
            return ValidationResult.failure(msg)

        if self.max_date is not None and date_value > self.max_date:
            msg = self.error_message or f"Date must be on or before {self.max_date}"
            return ValidationResult.failure(msg)

        return ValidationResult.success(date_value)
