"""
Validation module - PyDAL-style input validators.

Provides validators compatible with PyDAL's IS_* pattern:
- String validators: IsNotEmpty, IsLength, IsMatch, IsAlphanumeric, IsSlug, IsIn
- Numeric validators: IsInt, IsFloat, IsIntInRange, IsFloatInRange
- Network validators: IsEmail, IsURL, IsIPAddress
- DateTime validators: IsDate, IsDateTime, IsTime
- Password validators: IsStrongPassword

Usage:
    from py_libs.validation import IsEmail, IsLength, chain

    # Single validator
    validator = IsEmail()
    result = validator("user@example.com")

    # Chained validators
    validators = chain(IsNotEmpty(), IsLength(3, 255), IsEmail())
    result = validators("user@example.com")
"""

from py_libs.validation.base import (
    ValidationError,
    ValidationResult,
    Validator,
    chain,
)
from py_libs.validation.string import (
    IsAlphanumeric,
    IsIn,
    IsLength,
    IsMatch,
    IsNotEmpty,
    IsSlug,
    IsTrimmed,
)
from py_libs.validation.numeric import (
    IsFloat,
    IsFloatInRange,
    IsInt,
    IsIntInRange,
    IsNegative,
    IsPositive,
)
from py_libs.validation.network import (
    IsEmail,
    IsHostname,
    IsIPAddress,
    IsURL,
)
from py_libs.validation.datetime import (
    IsDate,
    IsDateInRange,
    IsDateTime,
    IsTime,
)
from py_libs.validation.password import (
    IsStrongPassword,
    PasswordOptions,
)

__all__ = [
    # Base
    "ValidationError",
    "ValidationResult",
    "Validator",
    "chain",
    # String
    "IsNotEmpty",
    "IsLength",
    "IsMatch",
    "IsAlphanumeric",
    "IsSlug",
    "IsIn",
    "IsTrimmed",
    # Numeric
    "IsInt",
    "IsFloat",
    "IsIntInRange",
    "IsFloatInRange",
    "IsPositive",
    "IsNegative",
    # Network
    "IsEmail",
    "IsURL",
    "IsIPAddress",
    "IsHostname",
    # DateTime
    "IsDate",
    "IsDateTime",
    "IsTime",
    "IsDateInRange",
    # Password
    "IsStrongPassword",
    "PasswordOptions",
]
