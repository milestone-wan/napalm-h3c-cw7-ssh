#
# Copyright 2022 milestone. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#

"""Live device integration tests.

Usage:
    pytest --live                            # test all devices in live_devices.yaml
    pytest --live --live-device=s6805        # test a specific device
    pytest --live --live-tag=router          # test devices by tag
"""

import pytest

from tests.conftest import _sanitize_output

# NAPALM standard getters that return structured data
_GETTERS = [
    "get_facts",
    "get_interfaces",
    "get_interfaces_ip",
    "get_interfaces_counters",
    "get_lldp_neighbors",
    "get_lldp_neighbors_detail",
    "get_arp_table",
    "get_mac_address_table",
    "get_vlans",
    "get_config",
    "get_environment",
    "get_ntp_stats",
    "get_ntp_peers",
    "get_ntp_servers",
    "get_snmp_information",
    "get_users",
    "get_optics",
    "get_ipv6_neighbors_table",
    "get_bgp_neighbors",
    "get_bgp_neighbors_detail",
    "get_bgp_config",
    "get_probes_config",
    "get_probes_results",
    "get_route_to",
    "get_network_instances",
    "get_irf_config",
    "get_mac_address_move_table",
    "get_firewall_policies",
    "is_irf",
]


@pytest.mark.live
class TestConnectivity:
    """Basic connectivity tests."""

    def test_is_alive(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            result = driver.is_alive()
            assert result.get("is_alive") is True, f"{name}: device not alive"

    def test_profile_discovered(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            assert driver.profile is not None, f"{name}: profile not discovered"
            assert driver.profile.major_version is not None, (
                f"{name}: major_version not detected"
            )


@pytest.mark.live
class TestGetters:
    """Test each getter returns valid data without errors."""

    @pytest.mark.parametrize("getter_name", _GETTERS)
    def test_getter_no_error(self, live_device_drivers, getter_name):
        for name, driver in live_device_drivers.items():
            func = getattr(driver, getter_name, None)
            if func is None:
                pytest.skip(f"{name}: {getter_name} not implemented")
            try:
                result = func()
            except NotImplementedError:
                pytest.skip(f"{name}: {getter_name} not implemented")
            except Exception as e:
                sanitized = _sanitize_output(str(e))
                pytest.fail(f"{name}: {getter_name} raised {type(e).__name__}: {sanitized}")


@pytest.mark.live
class TestGetFacts:
    """Detailed validation of get_facts output."""

    def test_facts_structure(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            facts = driver.get_facts()
            assert isinstance(facts, dict), f"{name}: facts is not a dict"
            # Required NAPALM fields
            for field in ("vendor", "model", "hostname", "uptime", "os_version",
                          "serial_number", "fqdn", "interface_list"):
                assert field in facts, f"{name}: missing field '{field}'"
            assert isinstance(facts["interface_list"], list), (
                f"{name}: interface_list is not a list"
            )
            assert len(facts["interface_list"]) > 0, f"{name}: no interfaces found"


@pytest.mark.live
class TestGetInterfaces:
    """Detailed validation of get_interfaces output."""

    def test_interfaces_structure(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            interfaces = driver.get_interfaces()
            assert isinstance(interfaces, dict), f"{name}: interfaces is not a dict"
            assert len(interfaces) > 0, f"{name}: no interfaces returned"
            for iface, data in interfaces.items():
                assert "is_up" in data, f"{name}/{iface}: missing 'is_up'"
                assert "is_enabled" in data, f"{name}/{iface}: missing 'is_enabled'"


@pytest.mark.live
class TestGetInterfacesIP:
    """Detailed validation of get_interfaces_ip output."""

    def test_interfaces_ip_structure(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            result = driver.get_interfaces_ip()
            assert isinstance(result, dict), f"{name}: not a dict"
            for iface, ip_data in result.items():
                assert "ipv4" in ip_data or "ipv6" in ip_data, (
                    f"{name}/{iface}: no ipv4 or ipv6 data"
                )


@pytest.mark.live
class TestGetConfig:
    """Detailed validation of get_config output."""

    def test_config_structure(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            config = driver.get_config()
            assert isinstance(config, dict), f"{name}: not a dict"
            assert "running" in config, f"{name}: missing 'running'"
            assert "startup" in config, f"{name}: missing 'startup'"


@pytest.mark.live
class TestGetEnvironment:
    """Detailed validation of get_environment output."""

    def test_environment_structure(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            env = driver.get_environment()
            assert isinstance(env, dict), f"{name}: not a dict"
            # At least one category should exist
            assert len(env) > 0, f"{name}: empty environment data"


@pytest.mark.live
class TestPing:
    """Test ping functionality."""

    def test_ping_loopback(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            result = driver.ping("127.0.0.1")
            assert isinstance(result, dict), f"{name}: ping result is not a dict"
            assert "success" in result, f"{name}: missing 'success' in ping result"


@pytest.mark.live
class TestTraceroute:
    """Test traceroute functionality."""

    def test_traceroute_loopback(self, live_device_drivers):
        for name, driver in live_device_drivers.items():
            result = driver.traceroute("127.0.0.1")
            assert isinstance(result, dict), f"{name}: traceroute result is not a dict"
            assert "success" in result, f"{name}: missing 'success' in traceroute result"
