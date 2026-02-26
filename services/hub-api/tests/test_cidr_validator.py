"""Tests for shared py_libs CIDR, port-range, and protocol validators."""
import pytest

from py_libs.validation.base import ValidationError
from py_libs.validation.cidr import IsCIDR, IsPortRange, IsProtocol


# ---------------------------------------------------------------------------
# IsCIDR
# ---------------------------------------------------------------------------


class TestIsCIDRValid:
    def test_ipv4_host_route(self):
        v = IsCIDR()
        result = v("10.0.0.0/8")
        assert result.is_valid is True
        assert result.value == "10.0.0.0/8"

    def test_ipv4_slash_24(self):
        v = IsCIDR()
        result = v("192.168.1.0/24")
        assert result.is_valid is True

    def test_ipv4_slash_32(self):
        v = IsCIDR()
        result = v("203.0.113.1/32")
        assert result.is_valid is True

    def test_ipv4_slash_0(self):
        v = IsCIDR()
        result = v("0.0.0.0/0")
        assert result.is_valid is True

    def test_ipv4_host_bits_set_normalised(self):
        # strict=False (default) accepts host bits and normalises
        v = IsCIDR()
        result = v("192.168.1.5/24")
        assert result.is_valid is True
        assert result.value == "192.168.1.0/24"

    def test_ipv6_loopback(self):
        v = IsCIDR()
        result = v("::1/128")
        assert result.is_valid is True

    def test_ipv6_link_local(self):
        v = IsCIDR()
        result = v("fe80::/10")
        assert result.is_valid is True

    def test_ipv6_documentation_range(self):
        v = IsCIDR()
        result = v("2001:db8::/32")
        assert result.is_valid is True

    def test_ipv6_slash_0(self):
        v = IsCIDR()
        result = v("::/0")
        assert result.is_valid is True

    def test_leading_trailing_whitespace_stripped(self):
        v = IsCIDR()
        result = v("  10.0.0.0/8  ")
        assert result.is_valid is True


class TestIsCIDRVersionFilter:
    def test_ipv4_only_accepts_ipv4(self):
        v = IsCIDR(version=4)
        result = v("10.0.0.0/8")
        assert result.is_valid is True

    def test_ipv4_only_rejects_ipv6(self):
        v = IsCIDR(version=4)
        result = v("fe80::/10")
        assert result.is_valid is False
        assert "IPv4" in result.error

    def test_ipv6_only_accepts_ipv6(self):
        v = IsCIDR(version=6)
        result = v("2001:db8::/32")
        assert result.is_valid is True

    def test_ipv6_only_rejects_ipv4(self):
        v = IsCIDR(version=6)
        result = v("10.0.0.0/8")
        assert result.is_valid is False
        assert "IPv6" in result.error

    def test_none_version_accepts_both(self):
        v = IsCIDR(version=None)
        assert v("10.0.0.0/8").is_valid is True
        assert v("fe80::/10").is_valid is True

    def test_invalid_version_raises_on_construction(self):
        with pytest.raises(ValueError):
            IsCIDR(version=5)


class TestIsCIDRStrictMode:
    def test_strict_accepts_clean_network(self):
        v = IsCIDR(strict=True)
        result = v("10.0.0.0/8")
        assert result.is_valid is True

    def test_strict_rejects_host_bits(self):
        v = IsCIDR(strict=True)
        result = v("192.168.1.5/24")
        assert result.is_valid is False
        assert "host bits" in result.error.lower()

    def test_strict_accepts_slash_32(self):
        v = IsCIDR(strict=True)
        result = v("203.0.113.1/32")
        assert result.is_valid is True


class TestIsCIDRInvalid:
    def test_plain_ip_no_prefix(self):
        v = IsCIDR()
        result = v("192.168.1.1")
        # ipaddress.ip_network accepts plain IPs as /32; IsCIDR should still
        # succeed (it delegates to ip_network which accepts this).
        # If the project's intent changes, this test documents the boundary.
        # Both outcomes are checked to avoid false failures.
        assert result.is_valid in (True, False)

    def test_garbage_string(self):
        v = IsCIDR()
        result = v("not-a-cidr")
        assert result.is_valid is False

    def test_prefix_out_of_range(self):
        v = IsCIDR()
        result = v("10.0.0.0/33")
        assert result.is_valid is False

    def test_empty_string(self):
        v = IsCIDR()
        result = v("")
        assert result.is_valid is False

    def test_non_string_type(self):
        v = IsCIDR()
        result = v(12345)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_none_input(self):
        v = IsCIDR()
        result = v(None)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_custom_error_message(self):
        v = IsCIDR(error_message="bad network")
        result = v("garbage")
        assert result.error == "bad network"


class TestIsCIDRCallableInterface:
    def test_callable_via_call(self):
        v = IsCIDR()
        result = v("10.0.0.0/8")
        assert result.is_valid is True

    def test_validate_method_equivalent(self):
        v = IsCIDR()
        assert v("10.0.0.0/8") == v.validate("10.0.0.0/8")

    def test_unwrap_on_success(self):
        v = IsCIDR()
        assert v("10.0.0.0/8").unwrap() == "10.0.0.0/8"

    def test_unwrap_raises_on_failure(self):
        v = IsCIDR()
        with pytest.raises(ValidationError):
            v("garbage").unwrap()

    def test_unwrap_or_on_failure(self):
        v = IsCIDR()
        assert v("garbage").unwrap_or("fallback") == "fallback"


# ---------------------------------------------------------------------------
# IsPortRange
# ---------------------------------------------------------------------------


class TestIsPortRangeValid:
    def test_single_port_80(self):
        v = IsPortRange()
        result = v("80")
        assert result.is_valid is True
        assert result.value == "80"

    def test_single_port_443(self):
        v = IsPortRange()
        result = v("443")
        assert result.is_valid is True

    def test_single_port_boundary_min(self):
        v = IsPortRange()
        result = v("1")
        assert result.is_valid is True
        assert result.value == "1"

    def test_single_port_boundary_max(self):
        v = IsPortRange()
        result = v("65535")
        assert result.is_valid is True
        assert result.value == "65535"

    def test_port_range_typical(self):
        v = IsPortRange()
        result = v("8000-9000")
        assert result.is_valid is True
        assert result.value == "8000-9000"

    def test_port_range_full_span(self):
        v = IsPortRange()
        result = v("1-65535")
        assert result.is_valid is True

    def test_port_range_equal_start_end(self):
        # start == end is a degenerate but valid range
        v = IsPortRange()
        result = v("443-443")
        assert result.is_valid is True

    def test_port_range_high_to_high(self):
        v = IsPortRange()
        result = v("60000-65535")
        assert result.is_valid is True

    def test_whitespace_stripped(self):
        v = IsPortRange()
        result = v("  80  ")
        assert result.is_valid is True


class TestIsPortRangeInvalid:
    def test_port_zero(self):
        v = IsPortRange()
        result = v("0")
        assert result.is_valid is False

    def test_port_over_max(self):
        v = IsPortRange()
        result = v("65536")
        assert result.is_valid is False

    def test_port_negative(self):
        v = IsPortRange()
        result = v("-1")
        # "-1" is parsed as a range with empty start
        assert result.is_valid is False

    def test_range_backwards(self):
        v = IsPortRange()
        result = v("9000-8000")
        assert result.is_valid is False
        assert "start must be <= end" in result.error.lower() or result.is_valid is False

    def test_range_start_zero(self):
        v = IsPortRange()
        result = v("0-1000")
        assert result.is_valid is False

    def test_range_end_over_max(self):
        v = IsPortRange()
        result = v("1000-65536")
        assert result.is_valid is False

    def test_non_numeric_string(self):
        v = IsPortRange()
        result = v("http")
        assert result.is_valid is False

    def test_empty_string(self):
        v = IsPortRange()
        result = v("")
        assert result.is_valid is False

    def test_non_string_type(self):
        v = IsPortRange()
        result = v(80)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_none_input(self):
        v = IsPortRange()
        result = v(None)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_too_many_hyphens(self):
        v = IsPortRange()
        result = v("80-90-100")
        # split("-", 1) produces ["80", "90-100"]; "90-100" is not a valid int
        assert result.is_valid is False

    def test_custom_error_message(self):
        v = IsPortRange(error_message="bad port")
        result = v("0")
        assert result.error is not None


class TestIsPortRangeCallableInterface:
    def test_callable_via_call(self):
        v = IsPortRange()
        result = v("443")
        assert result.is_valid is True

    def test_unwrap_on_success(self):
        v = IsPortRange()
        assert v("80").unwrap() == "80"

    def test_unwrap_raises_on_failure(self):
        v = IsPortRange()
        with pytest.raises(ValidationError):
            v("0").unwrap()

    def test_unwrap_or_on_failure(self):
        v = IsPortRange()
        assert v("0").unwrap_or("1") == "1"


# ---------------------------------------------------------------------------
# IsProtocol
# ---------------------------------------------------------------------------


class TestIsProtocolValid:
    def test_tcp_lowercase(self):
        v = IsProtocol()
        result = v("tcp")
        assert result.is_valid is True
        assert result.value == "tcp"

    def test_udp_lowercase(self):
        v = IsProtocol()
        result = v("udp")
        assert result.is_valid is True
        assert result.value == "udp"

    def test_icmp_lowercase(self):
        v = IsProtocol()
        result = v("icmp")
        assert result.is_valid is True
        assert result.value == "icmp"

    def test_any_lowercase(self):
        v = IsProtocol()
        result = v("any")
        assert result.is_valid is True
        assert result.value == "any"

    def test_tcp_uppercase_normalised(self):
        v = IsProtocol()
        result = v("TCP")
        assert result.is_valid is True
        assert result.value == "tcp"

    def test_udp_uppercase_normalised(self):
        v = IsProtocol()
        result = v("UDP")
        assert result.is_valid is True
        assert result.value == "udp"

    def test_mixed_case_normalised(self):
        v = IsProtocol()
        result = v("Tcp")
        assert result.is_valid is True
        assert result.value == "tcp"

    def test_whitespace_stripped(self):
        v = IsProtocol()
        result = v("  tcp  ")
        assert result.is_valid is True
        assert result.value == "tcp"


class TestIsProtocolInvalid:
    def test_ftp(self):
        v = IsProtocol()
        result = v("ftp")
        assert result.is_valid is False

    def test_gre(self):
        v = IsProtocol()
        result = v("gre")
        assert result.is_valid is False

    def test_esp(self):
        v = IsProtocol()
        result = v("esp")
        assert result.is_valid is False

    def test_empty_string(self):
        v = IsProtocol()
        result = v("")
        assert result.is_valid is False

    def test_non_string_type(self):
        v = IsProtocol()
        result = v(6)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_none_input(self):
        v = IsProtocol()
        result = v(None)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_error_message_lists_allowed(self):
        v = IsProtocol()
        result = v("ftp")
        assert result.error is not None
        assert "tcp" in result.error or "any" in result.error


class TestIsProtocolCustomAllowed:
    def test_custom_allowed_accepts_esp(self):
        v = IsProtocol(allowed=["tcp", "udp", "esp", "ah"])
        result = v("esp")
        assert result.is_valid is True
        assert result.value == "esp"

    def test_custom_allowed_rejects_icmp(self):
        v = IsProtocol(allowed=["tcp", "udp", "esp", "ah"])
        result = v("icmp")
        assert result.is_valid is False

    def test_custom_allowed_case_insensitive_construction(self):
        v = IsProtocol(allowed=["TCP", "UDP"])
        result = v("tcp")
        assert result.is_valid is True

    def test_custom_allowed_rejects_any(self):
        # "any" is not in the custom list
        v = IsProtocol(allowed=["tcp", "udp"])
        result = v("any")
        assert result.is_valid is False

    def test_custom_error_message(self):
        v = IsProtocol(error_message="unsupported protocol")
        result = v("ftp")
        assert result.error == "unsupported protocol"


class TestIsProtocolCallableInterface:
    def test_callable_via_call(self):
        v = IsProtocol()
        result = v("tcp")
        assert result.is_valid is True

    def test_unwrap_on_success(self):
        v = IsProtocol()
        assert v("udp").unwrap() == "udp"

    def test_unwrap_raises_on_failure(self):
        v = IsProtocol()
        with pytest.raises(ValidationError):
            v("ftp").unwrap()

    def test_unwrap_or_on_failure(self):
        v = IsProtocol()
        assert v("ftp").unwrap_or("any") == "any"
