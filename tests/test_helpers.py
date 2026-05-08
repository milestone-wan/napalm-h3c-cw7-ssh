"""Unit tests for napalm_h3c_comware.utils.helpers."""

import pytest

from napalm_h3c_comware.utils.helpers import (
    canonical_interface_name_comware,
    parse_null,
    parse_time,
)


class TestParseNull:
    def test_none_returns_default(self):
        assert parse_null(None, -1) == -1

    def test_empty_string_returns_default(self):
        assert parse_null("", -1) == -1

    def test_value_returned_when_present(self):
        assert parse_null("42", -1) == "42"

    def test_func_applied_to_value(self):
        assert parse_null("42", -1, int) == 42

    def test_func_not_applied_to_default(self):
        assert parse_null(None, -1, int) == -1

    def test_empty_string_with_func(self):
        assert parse_null("", 0, int) == 0


class TestParseTime:
    def test_seconds_only(self):
        assert parse_time("30 second") == 30

    def test_minutes_and_seconds(self):
        assert parse_time("1 minute 30 second") == 90

    def test_hours_minutes_seconds(self):
        assert parse_time("1 hour 2 minute 3 second") == 3723

    def test_days(self):
        assert parse_time("2 day 1 hour") == 2 * 86400 + 3600

    def test_weeks(self):
        assert parse_time("1 week 2 day") == 7 * 86400 + 2 * 86400

    def test_years(self):
        assert parse_time("1 year") == 365 * 86400

    def test_empty_string(self):
        assert parse_time("") == 0

    def test_complex_duration(self):
        expected = 365 * 86400 + 7 * 86400 + 86400 + 3600 + 60 + 1
        assert parse_time("1 year 1 week 1 day 1 hour 1 minute 1 second") == expected


class TestCanonicalInterfaceNameComware:
    def test_xge_expansion(self):
        assert canonical_interface_name_comware("XGE1/0/1") == "Ten-GigabitEthernet1/0/1"

    def test_vlan_expansion(self):
        assert canonical_interface_name_comware("Vlan10") == "Vlan-interface10"

    def test_bagg_expansion(self):
        assert canonical_interface_name_comware("BAGG1") == "Bridge-Aggregation1"

    def test_loop_expansion(self):
        assert canonical_interface_name_comware("Loop0") == "LoopBack0"

    def test_full_name_unchanged(self):
        assert canonical_interface_name_comware("GigabitEthernet1/0/1") == "GigabitEthernet1/0/1"

    def test_mge_expansion(self):
        assert canonical_interface_name_comware("MGE0/0/0") == "M-GigabitEthernet0/0/0"
