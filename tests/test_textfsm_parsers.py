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


class TestDisplayCurrentConfigurationNtpService:
    def test_parse(self):
        output = _read_fixture("display_current-configuration_ntp-service.txt")
        result = _parse("display_current-configuration_ntp-service", output)
        assert len(result) == 3
        entry = result[0]
        assert entry.get("address", "") != ""
        assert entry.get("association_type", "") != ""


class TestDisplaySnmpAgentSysInfo:
    def test_parse(self):
        output = _read_fixture("display_snmp-agent_sys-info.txt")
        result = _parse("display_snmp-agent_sys-info", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("chassis_id", "") != ""


class TestDisplayCurrentConfigurationSnmpCommunity:
    def test_parse(self):
        output = _read_fixture("display_current-configuration_snmp-community.txt")
        result = _parse("display_current-configuration_snmp-community", output)
        assert len(result) == 2
        entry = result[0]
        assert entry.get("community_name", "") != ""
        assert entry.get("mode", "") != ""


class TestDisplayCurrentConfigurationNqa:
    def test_parse(self):
        output = _read_fixture("display_current-configuration_nqa.txt")
        result = _parse("display_current-configuration_nqa", output)
        assert len(result) > 0
        # First record should have admin/test from nqa entry line
        entry_with_admin = [e for e in result if e.get("admin", "")]
        assert len(entry_with_admin) >= 2


class TestDisplayInterfaceCounters:
    def test_parse(self):
        output = _read_fixture("display_interface_counters.txt")
        result = _parse("display_interface_counters", output)
        assert len(result) > 0
        # Should have at least one interface name record
        iface_records = [e for e in result if e.get("interface", "")]
        assert len(iface_records) >= 1
        # Should have Input/Output section records
        section_records = [e for e in result if e.get("section", "")]
        assert len(section_records) >= 2


class TestDisplayLocalUser:
    def test_parse(self):
        output = _read_fixture("display_local-user.txt")
        result = _parse("display_local-user", output)
        assert len(result) > 0
        entry = result[0]
        assert entry.get("username", "") != ""
        assert entry.get("state", "") != ""


class TestDisplayNtpServiceSessions:
    def test_parse(self):
        output = _read_fixture("display_ntp-service_sessions.txt")
        result = _parse("display_ntp-service_sessions", output)
        assert len(result) == 2
        entry = result[0]
        assert entry.get("clock_source", "") != ""
        assert entry.get("clock_stratum", "") != ""


class TestDisplayIpv6Neighbors:
    def test_parse(self):
        output = _read_fixture("display_ipv6_neighbors.txt")
        result = _parse("display_ipv6_neighbors", output)
        assert len(result) == 3
        entry = result[0]
        assert entry.get("ipv6_address", "") != ""
        assert entry.get("interface", "") != ""


class TestDisplayNqaResult:
    def test_parse(self):
        output = _read_fixture("display_nqa_result.txt")
        result = _parse("display_nqa_result", output)
        assert len(result) >= 2
        entry = result[0]
        assert entry.get("admin", "") != ""
        assert entry.get("test", "") != ""
        assert entry.get("probe_count", "") != ""


class TestDisplayTransceiverDiagnosisInterface:
    def test_parse(self):
        output = _read_fixture("display_transceiver_diagnosis_interface.txt")
        result = _parse("display_transceiver_diagnosis_interface", output)
        assert len(result) == 2
        entry = result[0]
        assert entry.get("interface", "") != ""
        assert entry.get("tx_power", "") != ""
        assert entry.get("rx_power", "") != ""
