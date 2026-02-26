"""
CIDR and network-range validators - PyDAL-style validators for CIDR, port, and protocol inputs.

Provides:
- IsCIDR: Validates CIDR notation (IPv4 and IPv6)
- IsPortRange: Validates port or port-range strings
- IsProtocol: Validates network protocol strings
"""

from __future__ import annotations

import ipaddress

from py_libs.validation.base import ValidationResult, Validator


class IsCIDR(Validator[str, str]):
    """
    Validates that a string is a valid CIDR notation block.

    Uses Python's ipaddress.ip_network() for validation. By default host
    bits may be set (strict=False), meaning "192.168.1.5/24" is accepted
    and normalised to "192.168.1.0/24". Set strict=True to require that
    host bits are zero.

    Args:
        version: IP version to accept (4, 6, or None for both)
        strict: When True, host bits must be zero (default False)
        error_message: Custom error message override

    Example:
        validator = IsCIDR()
        result = validator("10.0.0.0/8")       # Valid -> "10.0.0.0/8"
        result = validator("192.168.1.5/24")    # Valid -> "192.168.1.0/24"
        result = validator("fe80::/10")         # Valid
        result = validator("not-a-cidr")        # Invalid

        validator = IsCIDR(version=4)
        result = validator("fe80::/10")         # Invalid (IPv6 not allowed)

        validator = IsCIDR(strict=True)
        result = validator("192.168.1.5/24")    # Invalid (host bits set)
    """

    def __init__(
        self,
        version: int | None = None,
        strict: bool = False,
        error_message: str | None = None,
    ) -> None:
        if version is not None and version not in (4, 6):
            raise ValueError("version must be 4, 6, or None")
        self.version = version
        self.strict = strict
        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        cidr_str = value.strip()
        if not cidr_str:
            return ValidationResult.failure(self._get_error_message())

        try:
            network = ipaddress.ip_network(cidr_str, strict=self.strict)
        except ValueError:
            if self.strict and "/" in cidr_str:
                # Provide a more helpful message when strict mode likely caused the failure
                try:
                    ipaddress.ip_network(cidr_str, strict=False)
                    return ValidationResult.failure(
                        "Invalid CIDR notation: host bits must be zero"
                    )
                except ValueError:
                    pass
            return ValidationResult.failure(self._get_error_message())

        # Check version if specified
        if self.version == 4 and network.version != 4:
            return ValidationResult.failure("CIDR must be an IPv4 network")
        if self.version == 6 and network.version != 6:
            return ValidationResult.failure("CIDR must be an IPv6 network")

        return ValidationResult.success(str(network))

    def _get_error_message(self) -> str:
        if self.error_message:
            return self.error_message
        if self.version == 4:
            return "Invalid CIDR notation: expected an IPv4 network (e.g. 10.0.0.0/8)"
        if self.version == 6:
            return "Invalid CIDR notation: expected an IPv6 network (e.g. fe80::/10)"
        return "Invalid CIDR notation (e.g. 10.0.0.0/8 or fe80::/10)"


class IsPortRange(Validator[str, str]):
    """
    Validates a port or port-range string.

    Accepts:
    - Single port: "80", "443", "8080"
    - Port range:  "8000-9000", "1024-65535"

    Ports must be in the range 1-65535 and, for ranges, the start port must
    be less than or equal to the end port.

    Args:
        error_message: Custom error message override

    Example:
        validator = IsPortRange()
        result = validator("80")          # Valid -> "80"
        result = validator("8080-8090")   # Valid -> "8080-8090"
        result = validator("0")           # Invalid (port 0 not allowed)
        result = validator("9000-8000")   # Invalid (start > end)
        result = validator("abc")         # Invalid
    """

    _MIN_PORT = 1
    _MAX_PORT = 65535

    def __init__(self, error_message: str | None = None) -> None:
        self.error_message = error_message or "Invalid port or port range"

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        port_str = value.strip()
        if not port_str:
            return ValidationResult.failure(self.error_message)

        if "-" in port_str:
            parts = port_str.split("-", 1)
            if len(parts) != 2:
                return ValidationResult.failure(self.error_message)

            start_str, end_str = parts[0].strip(), parts[1].strip()

            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                return ValidationResult.failure(self.error_message)

            if not (self._MIN_PORT <= start <= self._MAX_PORT):
                return ValidationResult.failure(
                    f"Invalid port range: start port must be between "
                    f"{self._MIN_PORT} and {self._MAX_PORT}"
                )
            if not (self._MIN_PORT <= end <= self._MAX_PORT):
                return ValidationResult.failure(
                    f"Invalid port range: end port must be between "
                    f"{self._MIN_PORT} and {self._MAX_PORT}"
                )
            if start > end:
                return ValidationResult.failure(
                    "Invalid port range: start must be <= end"
                )

            return ValidationResult.success(f"{start}-{end}")

        # Single port
        try:
            port = int(port_str)
        except ValueError:
            return ValidationResult.failure(self.error_message)

        if not (self._MIN_PORT <= port <= self._MAX_PORT):
            return ValidationResult.failure(
                f"Invalid port: must be between {self._MIN_PORT} and {self._MAX_PORT}"
            )

        return ValidationResult.success(str(port))


class IsProtocol(Validator[str, str]):
    """
    Validates a network protocol string.

    By default the allowed protocols are: tcp, udp, icmp, any.
    Matching is case-insensitive; the validated value is always normalised
    to lowercase.

    Args:
        allowed: Override the set of allowed protocol strings
        error_message: Custom error message override

    Example:
        validator = IsProtocol()
        result = validator("TCP")    # Valid -> "tcp"
        result = validator("udp")    # Valid -> "udp"
        result = validator("any")    # Valid -> "any"
        result = validator("ftp")    # Invalid

        validator = IsProtocol(allowed=["tcp", "udp", "esp", "ah"])
        result = validator("esp")    # Valid -> "esp"
        result = validator("icmp")   # Invalid (not in custom set)
    """

    _DEFAULT_ALLOWED = frozenset({"tcp", "udp", "icmp", "any"})

    def __init__(
        self,
        allowed: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        if allowed is not None:
            self.allowed = frozenset(p.lower() for p in allowed)
        else:
            self.allowed = self._DEFAULT_ALLOWED
        self.error_message = error_message

    def validate(self, value: str) -> ValidationResult[str]:
        if not isinstance(value, str):
            return ValidationResult.failure("Value must be a string")

        protocol = value.strip().lower()
        if not protocol:
            return ValidationResult.failure(self._get_error_message())

        if protocol not in self.allowed:
            return ValidationResult.failure(self._get_error_message())

        return ValidationResult.success(protocol)

    def _get_error_message(self) -> str:
        if self.error_message:
            return self.error_message
        allowed_sorted = ", ".join(sorted(self.allowed))
        return f"Invalid protocol: must be one of: {allowed_sorted}"
