"""TextFSM parser tests using synthetic CLI output fixtures.

Each test reads a synthetic CLI output file from tests/fixtures/,
parses it with the corresponding TextFSM template, and validates
the parsed structure and key fields.

NOTE: These fixtures are synthetic (not from real devices). They should
be replaced with real production output when available.
"""

import os

import pytest
from textfsm import TextFSM

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "napalm_h3c_comware", "utils", "textfsm_templates"
)


def _parse(template_name, raw_text):
    """Parse raw CLI text with a TextFSM template and return list of dicts.

    Keys are lowercased to match the behavior of napalm's textfsm_extractor.
    """
    template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.tpl")
    with open(template_path, encoding="utf-8") as f:
        fsm = TextFSM(f)
    result = fsm.ParseText(raw_text)
    return [{k.lower(): v for k, v in zip(fsm.header, row)} for row in result]


def _read_fixture(filename):
    """Read a fixture file and return its content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


class TestDisplayVersion:
    def test_parse(self):
        output = _read_fixture("display_version.txt")
        result = _parse("display_version", output)
        assert len(result) > 0
        entry = result[0]
        assert "software_version" in entry or "os_version" in entry


class TestDisplayInterface:
    def test_parse(self):
        output = _read_fixture("display_interface.txt")
        result = _parse("display_interface", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("interface", "") != ""


class TestDisplayIpInterface:
    def test_parse(self):
        output = _read_fixture("display_ip_interface.txt")
        result = _parse("display_ip_interface", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("interface", "") != ""
        assert len(entry.get("ip_address", [])) > 0


class TestDisplayIpv6Interface:
    def test_parse(self):
        output = _read_fixture("display_ipv6_interface.txt")
        result = _parse("display_ipv6_interface", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("interface", "") != ""


class TestDisplayArp:
    def test_parse(self):
        output = _read_fixture("display_arp.txt")
        result = _parse("display_arp", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("ip_address", "") != ""


class TestDisplayCpuUsageSummary:
    def test_parse(self):
        output = _read_fixture("display_cpu-usage_summary.txt")
        result = _parse("display_cpu-usage_summary", output)
        assert len(result) > 0
        entry = result[0]
        assert "five_sec" in entry or "cpu_id" in entry


class TestDisplayMemory:
    def test_parse(self):
        output = _read_fixture("display_memory.txt")
        result = _parse("display_memory", output)
        assert len(result) > 0
        entry = result[0]
        assert "slot" in entry


class TestDisplayPower:
    def test_parse(self):
        output = _read_fixture("display_power.txt")
        result = _parse("display_power", output)
        assert len(result) > 0


class TestDisplayFan:
    def test_parse(self):
        output = _read_fixture("display_fan.txt")
        result = _parse("display_fan", output)
        assert len(result) > 0


class TestDisplayEnvironment:
    def test_parse(self):
        output = _read_fixture("display_environment.txt")
        result = _parse("display_environment", output)
        assert len(result) > 0


class TestDisplayLldpNeighborVerbose:
    def test_parse(self):
        output = _read_fixture("display_lldp_neighbor-information_verbose.txt")
        result = _parse("display_lldp_neighbor-information_verbose", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("local_interface", "") != ""


class TestDisplayMacAddress:
    def test_parse(self):
        output = _read_fixture("display_mac-address.txt")
        result = _parse("display_mac-address", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("mac_address", "") != ""


class TestDisplayMacAddressMacMove:
    def test_parse(self):
        output = _read_fixture("display_mac-address_mac-move.txt")
        result = _parse("display_mac-address_mac-move", output)
        assert len(result) > 0


class TestDisplayVlanAll:
    def test_parse(self):
        output = _read_fixture("display_vlan_all.txt")
        result = _parse("display_vlan_all", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("vlan_id", "") != ""


class TestDisplayIpRoutingTable:
    def test_parse(self):
        output = _read_fixture("display_ip_routing-table.txt")
        result = _parse("display_ip_routing-table", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("destination", "") != ""
        assert entry.get("protocol", "") != ""


class TestDisplayIpRoutingTableVerbose:
    def test_parse(self):
        output = _read_fixture("display_ip_routing-table_verbose.txt")
        result = _parse("display_ip_routing-table_verbose", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("destination", "") != ""
        assert entry.get("protocol", "") != ""


class TestDisplayBgp:
    def test_parse(self):
        output = _read_fixture("display_bgp.txt")
        result = _parse("display_bgp", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("router_id", "") != ""


class TestDisplayBgpPeerIpv4:
    def test_parse(self):
        output = _read_fixture("display_bgp_peer_ipv4.txt")
        result = _parse("display_bgp_peer_ipv4", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("peer", "") != ""


class TestDisplayBgpPeerVerbose:
    def test_parse(self):
        output = _read_fixture("display_bgp_peer_verbose.txt")
        result = _parse("display_bgp_peer_verbose", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("peer", "") != ""
        assert entry.get("state", "") != ""


class TestDisplayVpnInstance:
    def test_parse(self):
        output = _read_fixture("display_ip_vpn-instance.txt")
        result = _parse("display_ip_vpn-instance", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("vpn_instance_name", "") != ""


class TestDisplayVpnInstanceDetail:
    def test_parse(self):
        output = _read_fixture("display_ip_vpn-instance_instance-name.txt")
        result = _parse("display_ip_vpn-instance_instance-name", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("vpn_instance_name", "") != ""


class TestDisplayDeviceManuinfo:
    def test_parse(self):
        output = _read_fixture("display_device_manuinfo.txt")
        result = _parse("display_device_manuinfo", output)
        assert len(result) > 0


class TestDisplayIrfConfig:
    def test_parse(self):
        output = _read_fixture("display_current-configuration_configuration_irf-port.txt")
        result = _parse("display_current-configuration_configuration_irf-port", output)
        assert len(result) > 0
