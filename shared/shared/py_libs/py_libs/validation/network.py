"""
Network validators - PyDAL-style validators for network-related inputs.

Provides:
- IsEmail: Validates email addresses (RFC 5322)
- IsURL: Validates URLs
- IsIPAddress: Validates IPv4/IPv6 addresses
- IsHostname: Validates hostnames
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from py_libs.validation.base import ValidationResult, Validator


class IsEmail(Validator[str, str]):
    """
    Validates that a string is a valid email address.

    Uses RFC 5322 compliant regex pattern. Optionally normalizes
    the email to lowercase.

    Args:
        normalize: Whether to lowercase the email

    Example:
        validator = IsEmail()
        result = validator("user@example.com")  # Valid
        result = validator("invalid-email")     # Invalid
    """

    # RFC 5322 compliant email regex (simplified but robust)
    _EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
        r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )

    def __init__(self, normalize: bool = True, error_message: str | None = None) -> None:
        self.normalize = normalize
        self.error_message = error_message or "Invalid email address"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        email = value.strip()
        if not email:
            return ValidationResult.failure(self.error_message)

        # Check length constraints
        if len(email) > 254:
            return ValidationResult.failure(self.error_message)

        # Check local part length
        local_part = email.split("@")[0] if "@" in email else email
        if len(local_part) > 64:
            return ValidationResult.failure(self.error_message)

        if not self._EMAIL_PATTERN.match(email):
            return ValidationResult.failure(self.error_message)

        if self.normalize:
            email = email.lower()

        return ValidationResult.success(email)


class IsURL(Validator[str, str]):
    """
    Validates that a string is a valid URL.

    Args:
        require_tld: Require a top-level domain
        allowed_schemes: Allowed URL schemes (default: http, https)

    Example:
        validator = IsURL()
        result = validator("https://example.com")  # Valid
        result = validator("not-a-url")            # Invalid

        validator = IsURL(allowed_schemes=["ftp"])
        result = validator("ftp://files.example.com")  # Valid
    """

    def __init__(
        self,
        require_tld: bool = True,
        allowed_schemes: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.require_tld = require_tld
        self.allowed_schemes = set(allowed_schemes or ["http", "https"])
        self.error_message = error_message or "Invalid URL"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        url = value.strip()
        if not url:
            return ValidationResult.failure(self.error_message)

        try:
            parsed = urlparse(url)
        except Exception:
            return ValidationResult.failure(self.error_message)

        # Check scheme
        if not parsed.scheme:
            return ValidationResult.failure(self.error_message)

        if parsed.scheme.lower() not in self.allowed_schemes:
            return ValidationResult.failure(
                f"URL scheme must be one of: {', '.join(self.allowed_schemes)}"
            )

        # Check netloc (hostname)
        if not parsed.netloc:
            return ValidationResult.failure(self.error_message)

        # Check for TLD if required
        if self.require_tld:
            hostname = parsed.netloc.split(":")[0]  # Remove port
            hostname = hostname.split("@")[-1]  # Remove userinfo
            if "." not in hostname and hostname.lower() != "localhost":
                return ValidationResult.failure(self.error_message)

        return ValidationResult.success(url)


class IsIPAddress(Validator[str, str]):
    """
    Validates that a string is a valid IP address.

    Args:
        version: IP version to accept (4, 6, or None for both)

    Example:
        validator = IsIPAddress()
        result = validator("192.168.1.1")      # Valid
        result = validator("::1")              # Valid (IPv6)
        result = validator("not-an-ip")        # Invalid

        validator = IsIPAddress(version=4)
        result = validator("::1")              # Invalid (IPv6 not allowed)
    """

    def __init__(
        self,
        version: int | None = None,
        error_message: str | None = None,
    ) -> None:
        if version is not None and version not in (4, 6):
            raise ValueError("version must be 4, 6, or None")
        self.version = version
        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        ip_str = value.strip()
        if not ip_str:
            return ValidationResult.failure(self._get_error_message())

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return ValidationResult.failure(self._get_error_message())

        # Check version if specified
        if self.version == 4 and ip.version != 4:
            return ValidationResult.failure("Value must be a valid IPv4 address")
        if self.version == 6 and ip.version != 6:
            return ValidationResult.failure("Value must be a valid IPv6 address")

        return ValidationResult.success(ip_str)

    def _get_error_message(self) -> str:
        if self.error_message:
            return self.error_message
        if self.version == 4:
            return "Value must be a valid IPv4 address"
        if self.version == 6:
            return "Value must be a valid IPv6 address"
        return "Value must be a valid IP address"


class IsHostname(Validator[str, str]):
    """
    Validates that a string is a valid hostname.

    Validates according to RFC 1123 hostname rules.

    Args:
        allow_ip: Whether to allow IP addresses as hostnames
        require_tld: Whether to require a top-level domain

    Example:
        validator = IsHostname()
        result = validator("example.com")   # Valid
        result = validator("my-server")     # Valid
        result = validator("invalid..com")  # Invalid
    """

    # RFC 1123 hostname pattern
    _HOSTNAME_PATTERN = re.compile(
        r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$"  # Single label
    )
    _FULL_HOSTNAME_PATTERN = re.compile(
        r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$"
    )

    def __init__(
        self,
        allow_ip: bool = False,
        require_tld: bool = False,
        error_message: str | None = None,
    ) -> None:
        self.allow_ip = allow_ip
        self.require_tld = require_tld
        self.error_message = error_message or "Invalid hostname"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        hostname = value.strip().lower()
        if not hostname:
            return ValidationResult.failure(self.error_message)

        # Check total length
        if len(hostname) > 253:
            return ValidationResult.failure(self.error_message)

        # Check if it's an IP address
        if self.allow_ip:
            try:
                ipaddress.ip_address(hostname)
                return ValidationResult.success(hostname)
            except ValueError:
                pass  # Not an IP, continue with hostname validation

        # Validate hostname format
        if not self._FULL_HOSTNAME_PATTERN.match(hostname):
            return ValidationResult.failure(self.error_message)

        # Check TLD requirement
        if self.require_tld and "." not in hostname:
            return ValidationResult.failure("Hostname must have a top-level domain")

        return ValidationResult.success(hostname)
