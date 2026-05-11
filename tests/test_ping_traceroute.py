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

"""Unit tests for ping and traceroute methods."""

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
    d.send_command = MagicMock()
    return d


# ---------------------------------------------------------------------------
# ping — success
# ---------------------------------------------------------------------------

class TestPingSuccess:

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        driver.send_command.return_value = _read_fixture("ping_success.txt")
        self.driver = driver

    def test_returns_success_key(self):
        result = self.driver.ping("8.8.8.8")
        assert "success" in result
        assert "error" not in result

    def test_probes_sent(self):
        result = self.driver.ping("8.8.8.8")
        assert result["success"]["probes_sent"] == 5

    def test_packet_loss_zero(self):
        result = self.driver.ping("8.8.8.8")
        assert result["success"]["packet_loss"] == 0

    def test_rtt_values(self):
        result = self.driver.ping("8.8.8.8")
        assert result["success"]["rtt_min"] == 2.282
        assert result["success"]["rtt_max"] == 2.890
        assert result["success"]["rtt_avg"] == 2.462
        assert result["success"]["rtt_stddev"] == 0.226

    def test_results_list(self):
        result = self.driver.ping("8.8.8.8")
        assert len(result["success"]["results"]) == 5
        for entry in result["success"]["results"]:
            assert "ip_address" in entry
            assert "rtt" in entry
            assert isinstance(entry["rtt"], float)

    def test_command_construction_default(self):
        self.driver.ping("8.8.8.8")
        cmd = self.driver.send_command.call_args[0][0]
        assert "ping" in cmd
        assert "8.8.8.8" in cmd
        assert "-c 5" in cmd
        assert "-h 255" in cmd
        assert "-s 100" in cmd
        assert "-t 2000" in cmd  # timeout * 1000

    def test_command_construction_with_vrf(self):
        self.driver.ping("8.8.8.8", vrf="mgmt")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-vpn-instance mgmt" in cmd

    def test_command_construction_with_source(self):
        self.driver.ping("8.8.8.8", source="10.0.0.1")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-a 10.0.0.1" in cmd

    def test_command_construction_with_source_interface(self):
        self.driver.ping("8.8.8.8", source_interface="GigabitEthernet1/0/1")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-i GigabitEthernet1/0/1" in cmd

    def test_source_takes_precedence_over_source_interface(self):
        self.driver.ping("8.8.8.8", source="10.0.0.1",
                         source_interface="GigabitEthernet1/0/1")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-a 10.0.0.1" in cmd
        assert "-i" not in cmd


# ---------------------------------------------------------------------------
# ping — failure (100% packet loss)
# ---------------------------------------------------------------------------

class TestPingFailure:

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        driver.send_command.return_value = _read_fixture("ping_failure.txt")
        self.driver = driver

    def test_returns_success_with_packet_loss(self):
        result = self.driver.ping("192.168.1.1")
        assert "success" in result
        assert result["success"]["packet_loss"] == 5
        assert result["success"]["probes_sent"] == 5
        assert result["success"]["rtt_min"] == 0.0
        assert result["success"]["results"] == []


# ---------------------------------------------------------------------------
# ping — error
# ---------------------------------------------------------------------------

class TestPingError:

    def test_exception_returns_error(self, driver):
        driver.send_command.side_effect = Exception("Connection lost")
        result = driver.ping("8.8.8.8")
        assert "error" in result
        assert "Connection lost" in result["error"]

    def test_unknown_host_returns_error(self, driver):
        driver.send_command.return_value = "Error: Unknown host 999.999.999.999"
        result = driver.ping("999.999.999.999")
        assert "error" in result


# ---------------------------------------------------------------------------
# traceroute — success
# ---------------------------------------------------------------------------

class TestTracerouteSuccess:

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        driver.send_command.return_value = _read_fixture("traceroute_output.txt")
        self.driver = driver

    def test_returns_success_key(self):
        result = self.driver.traceroute("8.8.8.8")
        assert "success" in result
        assert "error" not in result

    def test_hop_count(self):
        result = self.driver.traceroute("8.8.8.8")
        assert len(result["success"]) == 3

    def test_hop_ids(self):
        result = self.driver.traceroute("8.8.8.8")
        assert 1 in result["success"]
        assert 2 in result["success"]
        assert 3 in result["success"]

    def test_probes_per_hop(self):
        result = self.driver.traceroute("8.8.8.8")
        for hop_id in result["success"]:
            assert "probes" in result["success"][hop_id]
            assert len(result["success"][hop_id]["probes"]) == 3

    def test_probe_structure(self):
        result = self.driver.traceroute("8.8.8.8")
        probe = result["success"][1]["probes"][1]
        assert "rtt" in probe
        assert "ip_address" in probe
        assert "host_name" in probe
        assert isinstance(probe["rtt"], float)

    def test_first_hop_data(self):
        result = self.driver.traceroute("8.8.8.8")
        hop1 = result["success"][1]
        assert hop1["probes"][1]["ip_address"] == "192.168.1.1"
        assert hop1["probes"][1]["host_name"] == "192.168.1.1"

    def test_command_construction_default(self):
        self.driver.traceroute("8.8.8.8")
        cmd = self.driver.send_command.call_args[0][0]
        assert "tracert" in cmd
        assert "8.8.8.8" in cmd
        assert "-m 255" in cmd
        assert "-w 2" in cmd

    def test_command_construction_with_vrf(self):
        self.driver.traceroute("8.8.8.8", vrf="mgmt")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-vpn-instance mgmt" in cmd

    def test_command_construction_with_source(self):
        self.driver.traceroute("8.8.8.8", source="10.0.0.1")
        cmd = self.driver.send_command.call_args[0][0]
        assert "-a 10.0.0.1" in cmd

    def test_read_timeout(self):
        self.driver.traceroute("8.8.8.8", ttl=30, timeout=3)
        kwargs = self.driver.send_command.call_args[1]
        assert kwargs.get("read_timeout", 0) >= 90


# ---------------------------------------------------------------------------
# traceroute — error
# ---------------------------------------------------------------------------

class TestTracerouteError:

    def test_exception_returns_error(self, driver):
        driver.send_command.side_effect = Exception("Connection lost")
        result = driver.traceroute("8.8.8.8")
        assert "error" in result
        assert "Connection lost" in result["error"]

    def test_unknown_host_returns_error(self, driver):
        driver.send_command.return_value = "Error: Unknown host invalid.host"
        result = driver.traceroute("invalid.host")
        assert "error" in result
