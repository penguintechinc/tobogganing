"""
Password validators - PyDAL-style validators for password strength.

Provides:
- IsStrongPassword: Configurable password strength validation
- PasswordOptions: Configuration dataclass for password requirements
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

from py_libs.validation.base import ValidationResult, Validator


@dataclass(slots=True, frozen=True)
class PasswordOptions:
    """
    Configuration options for password validation.

    Attributes:
        min_length: Minimum password length (default: 8)
        max_length: Maximum password length (default: 128)
        require_uppercase: Require at least one uppercase letter
        require_lowercase: Require at least one lowercase letter
        require_digit: Require at least one digit
        require_special: Require at least one special character
        special_chars: Set of allowed special characters
        disallow_spaces: Whether to disallow spaces in passwords
    """

    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?~`"
    disallow_spaces: bool = True

    @classmethod
    def weak(cls) -> PasswordOptions:
        """Weak password requirements (min 6 chars, no special requirements)."""
        return cls(
            min_length=6,
            require_uppercase=False,
            require_lowercase=False,
            require_digit=False,
            require_special=False,
        )

    @classmethod
    def moderate(cls) -> PasswordOptions:
        """Moderate password requirements (min 8 chars, letters and digits)."""
        return cls(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=False,
        )

    @classmethod
    def strong(cls) -> PasswordOptions:
        """Strong password requirements (min 12 chars, all character types)."""
        return cls(
            min_length=12,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=True,
        )

    @classmethod
    def enterprise(cls) -> PasswordOptions:
        """Enterprise password requirements (min 16 chars, all character types)."""
        return cls(
            min_length=16,
            max_length=256,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=True,
        )


class IsStrongPassword(Validator[str, str]):
    """
    Validates password strength based on configurable requirements.

    Args:
        options: PasswordOptions instance or use defaults
        **kwargs: Override individual options

    Example:
        # Using default options
        validator = IsStrongPassword()
        result = validator("MyP@ssw0rd!")  # Valid

        # Using preset
        validator = IsStrongPassword(options=PasswordOptions.strong())

        # Custom options
        validator = IsStrongPassword(min_length=12, require_special=True)
    """

    def __init__(
        self,
        options: PasswordOptions | None = None,
        error_message: str | None = None,
        **kwargs: bool | int | str,
    ) -> None:
        if options is not None:
            self.options = options
        else:
            # Apply kwargs overrides to defaults
            default_opts = PasswordOptions()
            opt_dict = {
                "min_length": kwargs.get("min_length", default_opts.min_length),
                "max_length": kwargs.get("max_length", default_opts.max_length),
                "require_uppercase": kwargs.get("require_uppercase", default_opts.require_uppercase),
                "require_lowercase": kwargs.get("require_lowercase", default_opts.require_lowercase),
                "require_digit": kwargs.get("require_digit", default_opts.require_digit),
                "require_special": kwargs.get("require_special", default_opts.require_special),
                "special_chars": kwargs.get("special_chars", default_opts.special_chars),
                "disallow_spaces": kwargs.get("disallow_spaces", default_opts.disallow_spaces),
            }
            self.options = PasswordOptions(**opt_dict)  # type: ignore[arg-type]

        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Password must be a string")

        errors: list[str] = []
        opts = self.options

        # Length checks
        if len(value) < opts.min_length:
            errors.append(f"Password must be at least {opts.min_length} characters")

        if len(value) > opts.max_length:
            errors.append(f"Password must be at most {opts.max_length} characters")

        # Space check
        if opts.disallow_spaces and " " in value:
            errors.append("Password cannot contain spaces")

        # Character type checks
        if opts.require_uppercase and not any(c.isupper() for c in value):
            errors.append("Password must contain at least one uppercase letter")

        if opts.require_lowercase and not any(c.islower() for c in value):
            errors.append("Password must contain at least one lowercase letter")

        if opts.require_digit and not any(c.isdigit() for c in value):
            errors.append("Password must contain at least one digit")

        if opts.require_special:
            special_set = set(opts.special_chars)
            if not any(c in special_set for c in value):
                errors.append(
                    f"Password must contain at least one special character ({opts.special_chars[:10]}...)"
                )

        if errors:
            if self.error_message:
                return ValidationResult.failure(self.error_message)
            return ValidationResult.failure("; ".join(errors))

        return ValidationResult.success(value)

    def get_strength_score(self, password: str) -> int:
        """
        Calculate a password strength score (0-100).

        This is a supplementary method for UI feedback.
        Higher scores indicate stronger passwords.

        Args:
            password: The password to score

        Returns:
            Integer score from 0 to 100
        """
        score = 0

        # Length contribution (up to 30 points)
        score += min(len(password) * 2, 30)

        # Character variety (up to 40 points)
        has_lower = any(c in string.ascii_lowercase for c in password)
        has_upper = any(c in string.ascii_uppercase for c in password)
        has_digit = any(c in string.digits for c in password)
        has_special = any(c in self.options.special_chars for c in password)

        variety = sum([has_lower, has_upper, has_digit, has_special])
        score += variety * 10

        # Unique character ratio (up to 20 points)
        if password:
            unique_ratio = len(set(password)) / len(password)
            score += int(unique_ratio * 20)

        # No common patterns bonus (up to 10 points)
        common_patterns = [
            r"^123",
            r"abc",
            r"qwerty",
            r"password",
            r"(.)\1{2,}",  # Repeated characters
        ]
        has_common = any(re.search(p, password.lower()) for p in common_patterns)
        if not has_common:
            score += 10

        return min(score, 100)
