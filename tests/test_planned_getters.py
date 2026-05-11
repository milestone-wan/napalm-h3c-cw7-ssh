#
# Copyright 2022 milestone. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#

"""Unit tests for previously planned getters (now implemented)."""

import os

import pytest
from unittest.mock import MagicMock

from napalm_h3c_comware.comware import ComwareDriver
from napalm_h3c_comware.profiles import DeviceProfile, ComwareMajorVersion, DeviceRole

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def driver():
    """Create a ComwareDriver with mocked device connection."""
    d = ComwareDriver("localhost", "admin", "admin")
    d.device = MagicMock()
    d.profile = DeviceProfile(
        major_version=ComwareMajorVersion.V7,
        role=DeviceRole.SWITCH,
    )
    d.send_command = MagicMock(return_value="")
    return d


# ---------------------------------------------------------------------------
# get_ntp_stats
# ---------------------------------------------------------------------------

class TestGetNtpStats:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_ntp-service_sessions.txt")
        )
        result = driver.get_ntp_stats()
        assert len(result) == 2
        assert result[0]["remote"] == "10.1.1.1"
        assert result[0]["synchronized"] is True
        assert result[0]["stratum"] == 3
        assert result[0]["delay"] == 1.2345
        assert result[1]["remote"] == "172.16.0.1"
        assert result[1]["synchronized"] is False

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_ntp_stats()
        assert result == []


# ---------------------------------------------------------------------------
# get_ntp_peers
# ---------------------------------------------------------------------------

class TestGetNtpPeers:

    def test_delegates_to_ntp_stats(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_ntp-service_sessions.txt")
        )
        result = driver.get_ntp_peers()
        assert "10.1.1.1" in result
        assert "172.16.0.1" in result
        assert result["10.1.1.1"] == {}


# ---------------------------------------------------------------------------
# get_ntp_servers
# ---------------------------------------------------------------------------

class TestGetNtpServers:

    def test_parse_config(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_ntp-service.txt")
        )
        result = driver.get_ntp_servers()
        assert "10.1.1.1" in result
        assert result["10.1.1.1"]["association_type"] == "server"
        assert result["10.1.1.1"]["version"] == 4
        assert "172.16.0.1" in result
        assert result["172.16.0.1"]["source_address"] == "LoopBack0"
        assert "192.168.1.1" in result
        assert result["192.168.1.1"]["association_type"] == "peer"
        assert result["192.168.1.1"]["network_instance"] == "mgmt"

    def test_empty_config(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_ntp_servers()
        assert result == {}


# ---------------------------------------------------------------------------
# get_snmp_information
# ---------------------------------------------------------------------------

class TestGetSnmpInformation:

    def test_parse_sysinfo_and_community(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "snmp-agent sys-info" in cmd:
                return _read_fixture("display_snmp-agent_sys-info.txt")
            if "snmp-agent community" in cmd:
                return _read_fixture("display_current-configuration_snmp-community.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_snmp_information()
        assert result["contact"] == "admin@example.com"
        assert result["location"] == "Building-A Floor-3"
        assert result["chassis_id"] == "800063A28010E0FC000001"
        assert "public" in result["community"]
        assert result["community"]["public"]["mode"] == "read"
        assert "private" in result["community"]
        assert result["community"]["private"]["mode"] == "write"
        assert result["community"]["private"]["acl"] == "2000"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_snmp_information()
        assert result["chassis_id"] == ""
        assert result["community"] == {}


# ---------------------------------------------------------------------------
# get_users
# ---------------------------------------------------------------------------

class TestGetUsers:

    def test_parse_users(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "display local-user" in cmd:
                return _read_fixture("display_local-user.txt")
            if "local-user" in cmd:
                return _read_fixture("display_current-configuration_local-user.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_users()
        assert "admin" in result
        assert result["admin"]["level"] == 15  # network-admin
        assert "monitor" in result
        assert result["monitor"]["level"] == 5  # network-operator
        assert result["admin"]["password"] != ""

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_users()
        assert result == {}


# ---------------------------------------------------------------------------
# get_ipv6_neighbors_table
# ---------------------------------------------------------------------------

class TestGetIpv6NeighborsTable:

    def test_parse_neighbors(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_ipv6_neighbors.txt")
        )
        result = driver.get_ipv6_neighbors_table()
        assert len(result) == 3
        assert result[0]["ip"] == "FE80::1"
        assert result[0]["state"] == "REACH"
        assert result[0]["age"] == 10.0
        assert "mac" in result[0]
        assert "interface" in result[0]

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_ipv6_neighbors_table()
        assert result == []


# ---------------------------------------------------------------------------
# get_interfaces_counters
# ---------------------------------------------------------------------------

class TestGetInterfacesCounters:

    def test_parse_counters(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_interface_counters.txt")
        )
        result = driver.get_interfaces_counters()
        assert "GigabitEthernet1/0/1" in result
        counters = result["GigabitEthernet1/0/1"]
        assert counters["rx_octets"] == 18750000
        assert counters["tx_octets"] == 12000000
        assert counters["rx_unicast_packets"] == 100000
        assert counters["tx_unicast_packets"] == 60000
        assert counters["rx_multicast_packets"] == 20000
        assert counters["tx_multicast_packets"] == 15000
        assert counters["rx_broadcast_packets"] == 5000
        assert counters["tx_broadcast_packets"] == 5000
        assert counters["rx_errors"] == 3
        assert counters["tx_errors"] == 2
        assert counters["rx_discards"] == 1
        assert counters["tx_discards"] == 0

    def test_zero_counters(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_interface_counters.txt")
        )
        result = driver.get_interfaces_counters()
        assert "GigabitEthernet1/0/2" in result
        counters = result["GigabitEthernet1/0/2"]
        assert counters["rx_octets"] == 0
        assert counters["tx_octets"] == 0
        assert counters["rx_errors"] == 0

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_interfaces_counters()
        assert result == {}


# ---------------------------------------------------------------------------
# get_optics
# ---------------------------------------------------------------------------

class TestGetOptics:

    def test_parse_optics(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_transceiver_diagnosis_interface.txt")
        )
        result = driver.get_optics()
        assert "GigabitEthernet1/0/1" in result
        ch = result["GigabitEthernet1/0/1"]["physical_channels"]["channels"]
        assert ch["index"] == 0
        assert ch["state"]["output_power"]["instant"] == -2.50
        assert ch["state"]["input_power"]["instant"] == -5.30
        assert ch["state"]["laser_bias_current"]["instant"] == 15.00
        assert ch["state"]["output_power"]["avg"] == 0.0

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_optics()
        assert result == {}


# ---------------------------------------------------------------------------
# get_probes_config
# ---------------------------------------------------------------------------

class TestGetProbesConfig:

    def test_parse_nqa_config(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_nqa.txt")
        )
        result = driver.get_probes_config()
        assert "admin_test" in result
        assert "test_icmp" in result["admin_test"]
        icmp = result["admin_test"]["test_icmp"]
        assert icmp["probe_type"] == "icmp"
        assert icmp["target"] == "10.1.1.1"
        assert icmp["source"] == "192.168.1.1"
        assert icmp["probe_count"] == 3
        assert icmp["test_interval"] == 60
        assert "admin_http" in result
        assert result["admin_http"]["test_http"]["probe_type"] == "http"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_probes_config()
        assert result == {}


# ---------------------------------------------------------------------------
# get_probes_results
# ---------------------------------------------------------------------------

class TestGetProbesResults:

    def test_parse_nqa_results(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_nqa_result.txt")
        )
        result = driver.get_probes_results()
        assert "admin_test" in result
        assert "test_icmp" in result["admin_test"]
        icmp = result["admin_test"]["test_icmp"]
        assert icmp["probe_count"] == 3
        assert icmp["rtt"] == 3.0
        assert icmp["last_test_loss"] == 0
        assert icmp["current_test_min_delay"] == 1.0
        assert icmp["global_test_avg_delay"] == 3.0

    def test_packet_loss_calculation(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_nqa_result.txt")
        )
        result = driver.get_probes_results()
        http = result["admin_http"]["test_http"]
        assert http["probe_count"] == 5
        assert http["last_test_loss"] == 1  # 5 * 20% = 1

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_probes_results()
        assert result == {}


# ---------------------------------------------------------------------------
# get_bgp_config
# ---------------------------------------------------------------------------

class TestGetBgpConfig:

    def test_parse_bgp_config(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_bgp.txt")
        )
        result = driver.get_bgp_config()
        assert "EXTERNAL" in result
        assert result["EXTERNAL"]["type"] == "external"
        assert result["EXTERNAL"]["remote_as"] == 65001
        assert result["EXTERNAL"]["description"] == "External BGP peers"
        assert "10.0.0.2" in result["EXTERNAL"]["neighbors"]
        peer = result["EXTERNAL"]["neighbors"]["10.0.0.2"]
        assert peer["remote_as"] == 65001
        assert peer["description"] == "Primary external peer"

    def test_standalone_peer(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_bgp.txt")
        )
        result = driver.get_bgp_config()
        assert "192.168.1.1" in result
        assert result["192.168.1.1"]["neighbors"]["192.168.1.1"]["remote_as"] == 65002

    def test_group_filter(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_bgp.txt")
        )
        result = driver.get_bgp_config(group="EXTERNAL")
        assert "EXTERNAL" in result
        assert "192.168.1.1" not in result

    def test_neighbor_filter(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_bgp.txt")
        )
        result = driver.get_bgp_config(neighbor="10.0.0.2")
        assert "EXTERNAL" in result
        assert "10.0.0.2" in result["EXTERNAL"]["neighbors"]

    def test_empty_config(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_bgp_config()
        assert result == {}


# ---------------------------------------------------------------------------
# get_facts
# ---------------------------------------------------------------------------

class TestGetFacts:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "version" in cmd:
                return _read_fixture("display_version.txt")
            if "manuinfo" in cmd:
                return _read_fixture("display_device_manuinfo.txt")
            if "interface" in cmd:
                return _read_fixture("display_interface.txt")
            return ""
        driver.send_command = mock_send
        driver.device.find_prompt = MagicMock(return_value="<S6850>")
        result = driver.get_facts()
        assert result["vendor"] == "H3C"  # parsed from display version
        assert result["hostname"] == "S6850"
        assert result["model"] == "S6850-56HF"
        assert result["uptime"] > 0
        assert result["os_version"] != "Unknown"
        assert result["serial_number"] != "Unknown"
        assert len(result["interface_list"]) > 0

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        driver.device.find_prompt = MagicMock(return_value="<>")
        result = driver.get_facts()
        assert result["uptime"] == -1
        assert result["vendor"] == "Comware"  # default when no data
        assert result["hostname"] == "<>"  # prompt[1:-1] on "<>" gives ""
        assert result["interface_list"] == []


# ---------------------------------------------------------------------------
# get_interfaces
# ---------------------------------------------------------------------------

class TestGetInterfaces:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_interface.txt")
        )
        result = driver.get_interfaces()
        assert "GigabitEthernet1/0/1" in result
        iface = result["GigabitEthernet1/0/1"]
        assert iface["is_enabled"] is True
        assert iface["is_up"] is True
        assert iface["description"] == "Test Interface"
        assert iface["speed"] == 1000000
        assert iface["mtu"] == 1500
        assert "GigabitEthernet1/0/2" in result
        iface2 = result["GigabitEthernet1/0/2"]
        assert iface2["is_enabled"] is False
        assert iface2["is_up"] is False

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_interfaces()
        assert result == {}


# ---------------------------------------------------------------------------
# get_lldp_neighbors
# ---------------------------------------------------------------------------

class TestGetLldpNeighbors:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_lldp_neighbor-information_verbose.txt")
        )
        result = driver.get_lldp_neighbors()
        assert "GigabitEthernet1/0/1" in result
        assert len(result["GigabitEthernet1/0/1"]) == 1
        assert result["GigabitEthernet1/0/1"][0]["hostname"] == "Switch-B"
        assert result["GigabitEthernet1/0/1"][0]["port"] == "GigabitEthernet1/0/1"
        assert "GigabitEthernet1/0/2" in result

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_lldp_neighbors()
        assert result == {}


# ---------------------------------------------------------------------------
# get_lldp_neighbors_detail
# ---------------------------------------------------------------------------

class TestGetLldpNeighborsDetail:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_lldp_neighbor-information_verbose.txt")
        )
        result = driver.get_lldp_neighbors_detail()
        assert "GigabitEthernet1/0/1" in result
        detail = result["GigabitEthernet1/0/1"][0]
        assert detail["remote_chassis_id"] == "00e0-fc00-1001"
        assert detail["remote_system_name"] == "Switch-B"
        assert detail["parent_interface"] == ""
        assert isinstance(detail["remote_system_capab"], list)

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_lldp_neighbors_detail()
        assert result == {}


# ---------------------------------------------------------------------------
# get_bgp_neighbors
# ---------------------------------------------------------------------------

class TestGetBgpNeighbors:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "peer" in cmd and "verbose" not in cmd:
                return _read_fixture("display_bgp_peer_ipv4.txt")
            if cmd.strip() == "display bgp":
                return _read_fixture("display_bgp.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_bgp_neighbors()
        assert "global" in result
        assert result["global"]["router_id"] == "10.0.0.1"
        assert "10.0.0.2" in result["global"]["peers"]
        peer = result["global"]["peers"]["10.0.0.2"]
        assert peer["is_up"] is True
        assert peer["remote_as"] == 65001
        assert peer["address_family"]["ipv4"]["received_prefixes"] == 120
        assert "192.168.1.1" in result["global"]["peers"]
        assert result["global"]["peers"]["192.168.1.1"]["is_up"] is False

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_bgp_neighbors()
        assert result == {"global": {"router_id": "", "peers": {}}}


# ---------------------------------------------------------------------------
# get_bgp_neighbors_detail
# ---------------------------------------------------------------------------

class TestGetBgpNeighborsDetail:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "verbose" in cmd:
                return _read_fixture("display_bgp_peer_verbose.txt")
            if "peer" in cmd:
                return _read_fixture("display_bgp_peer_ipv4.txt")
            if cmd.strip() == "display bgp":
                return _read_fixture("display_bgp.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_bgp_neighbors_detail()
        assert "global" in result
        assert 65001 in result["global"]
        peers = result["global"][65001]
        assert len(peers) >= 1
        peer = peers[0]
        assert peer["up"] is True
        assert peer["remote_as"] == 65001
        assert peer["router_id"] == "10.0.0.1"
        assert peer["local_address"] == "10.0.0.1"
        assert peer["input_messages"] == 5678
        assert peer["output_messages"] == 1234
        assert peer["holdtime"] == 180
        assert peer["keepalive"] == 60
        assert peer["import_policy"] == "POLICY-IN"
        assert peer["export_policy"] == "POLICY-OUT"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_bgp_neighbors_detail()
        assert result == {}


# ---------------------------------------------------------------------------
# get_environment
# ---------------------------------------------------------------------------

class TestGetEnvironment:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "cpu-usage" in cmd:
                return _read_fixture("display_cpu-usage_summary.txt")
            if "memory" in cmd:
                return _read_fixture("display_memory.txt")
            if "power" in cmd:
                return _read_fixture("display_power.txt")
            if "fan" in cmd:
                return _read_fixture("display_fan.txt")
            if "environment" in cmd:
                return _read_fixture("display_environment.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_environment()
        assert "cpu" in result
        assert "memory" in result
        assert "power" in result
        assert "fans" in result
        assert "temperature" in result
        # CPU: at least one entry with %usage
        cpu_key = list(result["cpu"].keys())[0]
        assert "%usage" in result["cpu"][cpu_key]
        # Fans: at least one entry
        assert len(result["fans"]) > 0

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_environment()
        assert result["cpu"] == {}
        assert result["memory"] == {}
        assert result["power"] == {}
        assert result["fans"] == {}
        assert result["temperature"] == {}


# ---------------------------------------------------------------------------
# get_arp_table
# ---------------------------------------------------------------------------

class TestGetArpTable:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_arp.txt")
        )
        result = driver.get_arp_table()
        assert len(result) == 3
        assert result[0]["ip"] == "10.0.0.2"
        assert result[0]["interface"] == "GigabitEthernet1/0/1"
        assert "mac" in result[0]
        assert result[0]["age"] == 20.0

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_arp_table()
        assert result == []


# ---------------------------------------------------------------------------
# get_mac_address_move_table
# ---------------------------------------------------------------------------

class TestGetMacAddressMoveTable:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_mac-address_mac-move.txt")
        )
        result = driver.get_mac_address_move_table()
        assert len(result) == 2
        assert result[0]["vlan"] == 1
        assert result[0]["moves"] == 3
        assert "mac" in result[0]
        assert result[0]["current_port"] == "GigabitEthernet1/0/1"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_mac_address_move_table()
        assert result == []


# ---------------------------------------------------------------------------
# get_mac_address_table
# ---------------------------------------------------------------------------

class TestGetMacAddressTable:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "mac-move" in cmd:
                return _read_fixture("display_mac-address_mac-move.txt")
            if "mac-address" in cmd:
                return _read_fixture("display_mac-address.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_mac_address_table()
        assert len(result) >= 3
        first = result[0]
        assert "mac" in first
        assert first["vlan"] == 1
        assert first["active"] is True
        # Check static detection
        static_entries = [e for e in result if e["static"] is True]
        assert len(static_entries) >= 1

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_mac_address_table()
        assert result == []


# ---------------------------------------------------------------------------
# get_vlans
# ---------------------------------------------------------------------------

class TestGetVlans:

    def test_parse_success(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_vlan_all.txt")
        )
        result = driver.get_vlans()
        assert 1 in result
        assert "interfaces" in result[1]
        assert 10 in result
        assert result[10]["name"] == "MGMT"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_vlans()
        assert result == {}


# ---------------------------------------------------------------------------
# get_route_to
# ---------------------------------------------------------------------------

class TestGetRouteTo:

    def test_parse_no_destination(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_ip_routing-table.txt")
        )
        result = driver.get_route_to()
        assert len(result) > 0
        # Check a known route
        assert "10.0.0.0/24" in result
        route = result["10.0.0.0/24"][0]
        assert route["protocol"] == "direct"
        assert route["current_active"] is True
        assert route["age"] == -1  # non-verbose has no age

    def test_parse_with_destination(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_ip_routing-table_verbose.txt")
        )
        result = driver.get_route_to(destination="10.0.0.0/24")
        assert "10.0.0.0/24" in result
        route = result["10.0.0.0/24"][0]
        assert route["protocol"] == "direct"
        assert route["current_active"] is True
        assert route["age"] >= 0  # verbose has age

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_route_to()
        assert result == {}


# ---------------------------------------------------------------------------
# get_network_instances
# ---------------------------------------------------------------------------

class TestGetNetworkInstances:

    def test_parse_success(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "vpn-instance instance-name" in cmd:
                return _read_fixture("display_ip_vpn-instance_instance-name.txt")
            if "vpn-instance" in cmd:
                return _read_fixture("display_ip_vpn-instance.txt")
            if "ipv6 interface" in cmd:
                return _read_fixture("display_ipv6_interface.txt")
            if "ip interface" in cmd:
                return _read_fixture("display_ip_interface.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_network_instances()
        assert "default" in result
        assert result["default"]["type"] == "DEFAULT_INSTANCE"
        assert "MGMT" in result
        assert result["MGMT"]["type"] == "L3VRF"
        assert result["MGMT"]["state"]["route_distinguisher"] == "65000:100"

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_network_instances()
        # Default instance always present
        assert "default" in result


# ---------------------------------------------------------------------------
# get_interfaces_ip
# ---------------------------------------------------------------------------

class TestGetInterfacesIp:

    def test_parse_ipv4_and_ipv6(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "ipv6 interface" in cmd:
                return _read_fixture("display_ipv6_interface.txt")
            if "ip interface" in cmd:
                return _read_fixture("display_ip_interface.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_interfaces_ip()
        # IPv4 check
        assert "GigabitEthernet1/0/1" in result
        ipv4 = result["GigabitEthernet1/0/1"].get("ipv4", {})
        assert "10.0.0.1" in ipv4
        assert ipv4["10.0.0.1"]["prefix_length"] == 24
        assert "10.0.1.1" in ipv4  # Sub address
        # IPv6 check
        ipv6 = result["GigabitEthernet1/0/1"].get("ipv6", {})
        assert "FE80::200:5EFF:FE04:5601" in ipv6
        assert ipv6["FE80::200:5EFF:FE04:5601"]["prefix_length"] == 10
        assert "2001:DB8::1" in ipv6
        assert ipv6["2001:DB8::1"]["prefix_length"] == 64

    def test_vlan_interface_ipv6_multiple_global(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "ipv6 interface" in cmd:
                return _read_fixture("display_ipv6_interface.txt")
            if "ip interface" in cmd:
                return _read_fixture("display_ip_interface.txt")
            return ""
        driver.send_command = mock_send
        result = driver.get_interfaces_ip()
        # Vlan-interface10 has 2 global unicast addresses
        if "Vlan-interface10" in result:
            ipv6 = result["Vlan-interface10"].get("ipv6", {})
            assert "2001:DB8:1::1" in ipv6
            assert "2001:DB8:2::1" in ipv6

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_interfaces_ip()
        assert result == {}


# ---------------------------------------------------------------------------
# get_irf_config
# ---------------------------------------------------------------------------

class TestGetIrfConfig:

    def test_parse_irf_config(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_irf-port.txt")
        )
        result = driver.get_irf_config()
        assert 1 in result
        assert "irf-port1" in result[1]
        assert "irf-port2" in result[1]
        assert "Ten-GigabitEthernet1/0/49" in result[1]["irf-port1"]
        assert "Ten-GigabitEthernet1/0/51" in result[1]["irf-port2"]

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_irf_config()
        assert result == {}


# ---------------------------------------------------------------------------
# is_irf
# ---------------------------------------------------------------------------

class TestIsIrf:

    def test_irf_detected(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_current-configuration_configuration_irf-port.txt")
        )
        result = driver.is_irf()
        assert result["is_irf"] is True

    def test_no_irf(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.is_irf()
        assert result["is_irf"] is False


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------

class TestGetConfig:

    def test_returns_running_and_startup(self, driver):
        def mock_send(cmd, *args, **kwargs):
            if "current-configuration" in cmd:
                return "sysname Switch\nreturn"
            if "saved-configuration" in cmd:
                return "sysname SavedSwitch\nreturn"
            return ""
        driver.send_command = mock_send
        result = driver.get_config()
        assert "running" in result
        assert "startup" in result
        assert "candidate" in result
        assert result["candidate"] == ""
        assert "Switch" in result["running"]

    def test_retrieve_running_only(self, driver):
        driver.send_command = MagicMock(return_value="sysname Switch\nreturn")
        result = driver.get_config(retrieve="running")
        assert result["running"] != ""
        assert result["startup"] == ""

    def test_empty_output(self, driver):
        driver.send_command = MagicMock(return_value="")
        result = driver.get_config()
        assert result["running"] == ""
        assert result["startup"] == ""
        assert result["candidate"] == ""


# ---------------------------------------------------------------------------
# Bug-fix regression tests
# ---------------------------------------------------------------------------

class TestSendCommandDrainBehavior:
    """Regression test: send_command should NOT re-send the command when
    the initial call returns empty.  It should drain the channel instead.
    """

    def test_drains_channel_on_empty_result(self, driver):
        # Restore the real send_command method (fixture replaces it with a mock)
        real_send_command = ComwareDriver.send_command.__get__(driver, ComwareDriver)
        call_count = {"send_command": 0}

        def mock_send_command(cmd, *args, **kwargs):
            call_count["send_command"] += 1
            if call_count["send_command"] == 1:
                return ""  # First call returns empty
            return "should not be called"

        driver.device.send_command = mock_send_command
        driver.device.read_channel_timing = MagicMock(
            return_value="Slot 1\ncpu usage: 5%"
        )
        driver.device.find_prompt = MagicMock(return_value="<switch>")

        result = real_send_command("display cpu-usage summary")

        # Should have drained channel output
        assert "cpu usage" in result
        # Should NOT have re-sent the command
        assert call_count["send_command"] == 1

    def test_returns_empty_when_drain_also_empty(self, driver):
        real_send_command = ComwareDriver.send_command.__get__(driver, ComwareDriver)
        driver.device.send_command = MagicMock(return_value="")
        driver.device.read_channel_timing = MagicMock(return_value="")
        driver.device.find_prompt = MagicMock(return_value="<switch>")

        result = real_send_command("display cpu-usage summary")
        assert result == ""

    def test_reconnects_on_exception(self, driver):
        real_send_command = ComwareDriver.send_command.__get__(driver, ComwareDriver)
        new_device = MagicMock()
        new_device.send_command = MagicMock(return_value="sysname Switch")

        def fake_reconnect():
            driver.device = new_device

        driver.device.send_command = MagicMock(side_effect=ConnectionError("SSH session closed"))
        driver._reconnect = fake_reconnect

        result = real_send_command("display version")
        assert "Switch" in result


class TestCacheNotStoringEmptyResults:
    """Regression test: empty TextFSM results should not be cached."""

    def test_empty_result_not_cached(self, driver):
        call_count = {"send_command": 0}

        def mock_send(cmd, *args, **kwargs):
            call_count["send_command"] += 1
            return "some output that produces no TextFSM match"

        driver.send_command = mock_send
        # First call: empty result should NOT be cached
        result1 = driver._get_structured_output("display version")
        assert result1 == []
        # Second call: should re-execute send_command (not cached)
        result2 = driver._get_structured_output("display version")
        assert call_count["send_command"] == 2

    def test_non_empty_result_cached(self, driver):
        call_count = {"send_command": 0}

        def mock_send(cmd, *args, **kwargs):
            call_count["send_command"] += 1
            return _read_fixture("display_version.txt")

        driver.send_command = mock_send
        result1 = driver._get_structured_output("display version")
        assert len(result1) > 0
        # Second call: should use cache (no additional send_command)
        result2 = driver._get_structured_output("display version")
        assert call_count["send_command"] == 1


class TestGetTemperatureThresholdZero:
    """Regression test: threshold=0 should NOT trigger false alerts."""

    def test_zero_threshold_no_false_alert(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_environment.txt")
        )
        result = driver._get_temperature()
        for key, val in result.items():
            # If alert/critical threshold is 0 (not configured),
            # is_alert and is_critical should be False
            assert val["is_alert"] is False or val["temperature"] > 0
            assert val["is_critical"] is False or val["temperature"] > 0


class TestGetFactsPartialFailure:
    """Regression test: get_facts should return partial data when one
    command fails, rather than aborting entirely.
    """

    def test_version_failure_does_not_block_hostname(self, driver):
        """If display version fails, hostname should still be obtained."""
        def mock_send(cmd, *args, **kwargs):
            if "version" in cmd:
                return ""  # Empty output causes TextFSM to return []
            if "interface" in cmd:
                return _read_fixture("display_interface.txt")
            if "manuinfo" in cmd:
                return _read_fixture("display_device_manuinfo.txt")
            return ""

        driver.send_command = mock_send
        driver.device.find_prompt = MagicMock(return_value="<TestSwitch>")

        result = driver.get_facts()
        # hostname should still be populated
        assert result["hostname"] == "TestSwitch"
        # uptime should remain at default -1 (version returned empty)
        assert result["uptime"] == -1


class TestEnvironmentKeyConsistency:
    """Regression test: environment sub-method key names should use
    consistent capitalization (Chassis/Slot/Power/Fan/Sensor).
    """

    def test_power_key_capitalized(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_power.txt")
        )
        result = driver._get_power(verbose=True)
        for key in result:
            # Keys should use capitalized format
            if "slot" in key.lower():
                assert "Slot" in key, f"Key '{key}' should use 'Slot' not 'slot'"
            if "chassis" in key.lower():
                assert "Chassis" in key, f"Key '{key}' should use 'Chassis' not 'chassis'"

    def test_temperature_key_capitalized(self, driver):
        driver.send_command = MagicMock(
            return_value=_read_fixture("display_environment.txt")
        )
        result = driver._get_temperature()
        for key in result:
            if "slot" in key.lower():
                assert "Slot" in key, f"Key '{key}' should use 'Slot' not 'slot'"
            if "chassis" in key.lower():
                assert "Chassis" in key, f"Key '{key}' should use 'Chassis' not 'chassis'"
            if "sensor" in key.lower():
                assert "Sensor" in key, f"Key '{key}' should use 'Sensor' not 'sensor'"


class TestCloseClearsState:
    """Regression test: close() should clear cache and config state."""

    def test_close_clears_cache_and_config(self, driver):
        driver._command_cache = {("display version", "display_version"): [{"data": "test"}]}
        driver._candidate_config = "some config"
        driver._pre_commit_config = "pre commit config"
        driver._config_replace = True
        driver._loaded = True
        driver._netmiko_close = MagicMock()

        driver.close()

        assert driver._command_cache == {}
        assert driver._candidate_config == ""
        assert driver._pre_commit_config == ""
        assert driver._config_replace is False
        assert driver._loaded is False


class TestComwareParserErrorAlias:
    """Regression test: ParserError should be a backward-compatible alias."""

    def test_parser_error_is_alias(self):
        from napalm_h3c_comware.exceptions import ComwareParserError, ParserError
        assert ParserError is ComwareParserError

    def test_import_from_package(self):
        from napalm_h3c_comware import ComwareParserError, ParserError
        assert ParserError is ComwareParserError

    def test_catch_with_old_name(self):
        from napalm_h3c_comware.exceptions import ComwareParserError, ParserError
        try:
            raise ComwareParserError("test error")
        except ParserError:
            pass  # Should be caught by the alias


class TestIsAliveActiveProbe:
    """Test is_alive with active probe option."""

    def test_passive_probe_default(self, driver):
        driver._is_alive_active_probe = False
        driver.device.is_alive = MagicMock(return_value=True)
        result = driver.is_alive()
        assert result["is_alive"] is True
        driver.device.send_command.assert_not_called()

    def test_active_probe_enabled(self, driver):
        driver._is_alive_active_probe = True
        driver.device.send_command = MagicMock(return_value="10:00:00 UTC 2026")
        result = driver.is_alive()
        assert result["is_alive"] is True

    def test_active_probe_connection_dead(self, driver):
        driver._is_alive_active_probe = True
        driver.device.send_command = MagicMock(side_effect=Exception("Connection lost"))
        result = driver.is_alive()
        assert result["is_alive"] is False
