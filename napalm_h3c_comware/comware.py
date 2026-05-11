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

"""
Napalm driver for H3C Comware V7/V9 devices.

Read https://napalm.readthedocs.io for more information.
"""

import difflib
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

from napalm.base import models
from napalm.base.base import NetworkDriver
from napalm.base.exceptions import (
    ReplaceConfigException,
    MergeConfigException,
    CommitConfirmException,
)
from napalm.base.helpers import (
    textfsm_extractor,
    mac,
    sanitize_configs,
    ip,
)
from napalm.base.netmiko_helpers import netmiko_args
from netmiko.hp.hp_comware import HPComwareBase
from netmiko.scp_handler import BaseFileTransfer

from .commands import default_command_registry
from .exceptions import ComwareParserError, UnsupportedCommandError, ConfigManagementError
from .profiles import build_device_profile
from .utils.helpers import (
    canonical_interface_name_comware,
    parse_time,
    parse_null,
    strptime,
    get_value_from_list_of_dict,
)

logger = logging.getLogger(__name__)

# Comware error patterns for config command output validation
COMWARE_CONFIG_ERROR_PATTERNS = [
    r"%\s*Unrecognized command",
    r"%\s*Ambiguous command",
    r"%\s*Incomplete command",
    r"%\s*Too many parameters",
    r"%\s*Wrong parameter",
    r"%\s*Wrong parameter type",
    r"%\s*Parameter error",
    r"%\s*Command not available in current view",
]

# H3C Comware sanitize filters for get_config(sanitized=True)
COMWARE_SANITIZE_FILTERS = {
    # SNMP community strings
    r"^(snmp-agent community (?:read|write)) .+$": r"\1 <removed>",
    # SNMPv3 USM user authentication / privacy keys
    r"^(snmp-agent usm-user v3 \S+(?:\s+\S+)* authentication-mode (?:md5|sha)) .+$": r"\1 <removed>",
    r"^(snmp-agent usm-user v3 \S+(?:\s+\S+)* privacy-mode (?:des56|aes128|3des)) .+$": r"\1 <removed>",
    # Local user passwords
    r"^(local-user \S+(?:\s+class\s+\S+)? password (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # Super password for role-based access
    r"^(super password role \S+ (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # Generic authentication-key lines
    r"^(\s*authentication-key (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # Generic key lines
    r"^(\s*key (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # NTP authentication key
    r"^(ntp-service authentication-keyid \d+ authentication-mode \S+ (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # IKE / IPsec pre-shared keys
    r"^(pre-shared-key (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # VTY / user-interface authentication password
    r"^(set authentication password (?:simple|cipher|hash)) .+$": r"\1 <removed>",
    # PPP authentication password
    r"^(ppp (?:chap|pap) password (?:simple|cipher|hash)) .+$": r"\1 <removed>",
}


class HPComwareFileTransfer(BaseFileTransfer):
    """FileTransfer subclass for H3C Comware devices.

    Adapts BaseFileTransfer methods to Comware's CLI output format:
    - ``dir`` output differs from Cisco
    - MD5 uses ``md5sum`` instead of ``verify /md5``
    - SCP uses ``scp server enable`` instead of ``ip scp server enable``
    """

    def check_file_exists(self, dest_file: str = "", file_system: str = "") -> bool:
        """Check if dest_file exists on the device using ``dir``."""
        if not dest_file:
            dest_file = self.dest_file
        if not file_system:
            file_system = self.file_system
        cmd = f"dir {file_system}/{dest_file}"
        output = self.ssh_ctl_chan.send_command(cmd, read_timeout=30)
        return "Error" not in output and dest_file in output

    def remote_file_size(self, dest_file: str = "", file_system: str = "") -> int:
        """Get remote file size from ``dir`` output."""
        if not dest_file:
            dest_file = self.dest_file
        if not file_system:
            file_system = self.file_system
        cmd = f"dir {file_system}/{dest_file}"
        output = self.ssh_ctl_chan.send_command(cmd, read_timeout=30)
        # Comware dir output: "  12345  Jan 01 00:00:00  file"
        match = re.search(r"\s+(\d+)\s+\w+\s+\d+\s+[\d:]+\s+" + re.escape(dest_file), output)
        if match:
            return int(match.group(1))
        raise IOError(f"Unable to determine file size for {dest_file}")

    def remote_space_available(self, search_pattern: str = "") -> int:
        """Check available space on the device filesystem."""
        if not search_pattern:
            search_pattern = self.file_system
        cmd = f"dir {search_pattern}"
        output = self.ssh_ctl_chan.send_command(cmd, read_timeout=30)
        # Comware: "xxx bytes available (xxx bytes free)" or similar
        match = re.search(r"(\d+)\s*(?:bytes\s+)?(?:available|free)", output, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # Fallback: return a large number if we can't parse
        logger.warning("Could not determine available space, assuming sufficient")
        return 1024 * 1024 * 1024  # 1 GB

    def remote_md5(self, base_cmd: str = "", dest_file: str = "") -> str:
        """Compute MD5 of remote file using ``md5sum``."""
        if not dest_file:
            dest_file = self.dest_file
        if not base_cmd:
            base_cmd = f"md5sum {self.file_system}/{dest_file}"
        output = self.ssh_ctl_chan.send_command(base_cmd, read_timeout=120)
        # md5sum output: "d41d8cd98f00b204e9800998ecf8427e  flash:/file"
        match = re.match(r"([0-9a-fA-F]{32})", output.strip())
        if match:
            return match.group(1)
        raise IOError(f"Could not compute MD5 for {dest_file}")

    def enable_scp(self, cmd: str = "") -> None:
        """Enable SCP server on Comware."""
        if not cmd:
            cmd = "scp server enable"
        self.ssh_ctl_chan.send_config_set([cmd], enter_config_mode=True, exit_config_mode=True)

    def disable_scp(self, cmd: str = "") -> None:
        """Disable SCP server on Comware."""
        if not cmd:
            cmd = "undo scp server enable"
        self.ssh_ctl_chan.send_config_set([cmd], enter_config_mode=True, exit_config_mode=True)


class ComwareDriver(NetworkDriver):
    """Napalm driver for H3C Comware7 network devices (using ssh)."""

    def __init__(
            self,
            hostname: str,
            username: str,
            password: str,
            timeout: int = 100,
            optional_args: Optional[Dict] = None):

        self.device = None
        if optional_args is None:
            optional_args = {}
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout
        self.force_english = optional_args.pop("force_english", True)
        self._resync_delay = optional_args.pop("resync_delay", 0.3)
        self._is_alive_active_probe = optional_args.pop("is_alive_active_probe", False)
        self.netmiko_optional_args = netmiko_args(optional_args)
        self.profile = None
        self.command_registry = default_command_registry()
        self._command_cache: Dict[Tuple[str, str], list] = {}

        # Configuration management state
        self._candidate_config: str = ""
        self._config_replace: bool = False
        self._loaded: bool = False
        self._pre_commit_config: str = ""

        # File transfer settings for replace mode
        self._dest_file_system = optional_args.pop("dest_file_system", "flash:")
        self._candidate_cfg = optional_args.pop("candidate_cfg", "candidate_config.txt")
        self._rollback_cfg = optional_args.pop("rollback_cfg", "rollback_config.txt")

    def open(self):
        """Open a connection to the device."""
        device_type = "hp_comware"
        self.device: HPComwareBase = self._netmiko_open(
            device_type, netmiko_optional_args=self.netmiko_optional_args
        )
        logger.info("Connected to %s", self.hostname)
        self._command_cache = {}

        # Disable terminal paging to prevent --More-- truncation on chassis devices
        try:
            self.device.send_command("screen-length disable", read_timeout=10)
        except Exception:
            logger.debug("screen-length disable failed (may not be supported)")

        if self.force_english:
            self._force_english_output()

        self._discover_profile()

    def close(self):
        logger.info("Disconnecting from %s", self.hostname)
        self._command_cache = {}
        self._candidate_config = ""
        self._pre_commit_config = ""
        self._config_replace = False
        self._loaded = False
        self._netmiko_close()

    def _resync_prompt(self):
        """Re-sync the session prompt after timing-based reads.

        Uses ``find_prompt`` with a short timeout to avoid blocking
        indefinitely on stale connections.
        """
        try:
            time.sleep(self._resync_delay)
            self.device.find_prompt(delay_factor=1)
        except Exception as e:
            logger.warning("Failed to re-sync prompt: %s", e)

    def send_command(self, command: str, *args, **kwargs):
        """Send a command to the device with automatic fallback.

        On chassis/frame devices (e.g. S12504G), ``send_command`` may fail
        due to prompt detection issues with long or multi-section output.
        When that happens, drain the remaining output using
        ``read_channel_timing`` (without re-sending the command), then
        re-sync the session prompt.

        IMPORTANT: The command is only sent ONCE in the normal path.
        If the initial ``send_command`` returns empty, we drain the
        already-sent command's output rather than re-sending, to avoid
        re-executing non-idempotent commands (config changes, reboots, etc.).
        """
        logger.debug("Sending command: %s", command)
        try:
            result = self.device.send_command(command, *args, **kwargs)
            if result is not None and result.strip():
                return result
            # send_command returned empty — likely prompt detection matched
            # stale buffer data.  The command was already sent to the device
            # so we drain remaining output WITHOUT re-sending.
            logger.debug(
                "send_command returned empty for '%s'; draining channel output",
                command,
            )
            try:
                read_timeout = kwargs.get("read_timeout", 30)
                drained = self.device.read_channel_timing(
                    last_read=2.0, read_timeout=read_timeout,
                )
                if drained and drained.strip():
                    logger.debug(
                        "Drained %d chars of output for '%s'",
                        len(drained), command,
                    )
                    self._resync_prompt()
                    return drained
            except Exception as drain_err:
                logger.debug("Channel drain failed for '%s': %s", command, drain_err)

            # Still empty after drain — re-sync prompt and return empty.
            # We do NOT re-send the command to avoid double-execution of
            # non-idempotent operations.
            logger.warning(
                "No output received for command '%s' (not re-sending to "
                "avoid double-execution)", command,
            )
            self._resync_prompt()
            return result if result is not None else ""

        except Exception as e:
            # Only reconnect on actual connection errors, not empty output
            logger.debug("send_command failed for '%s': %s", command, e)
            try:
                self._reconnect()
                result = self.device.send_command(command, *args, **kwargs)
                return result if result is not None else ""
            except Exception as e3:
                logger.error("Reconnect and retry failed: %s", e3)
                raise

    def _reconnect(self):
        """Attempt to re-establish the SSH connection."""
        logger.info("Attempting reconnect to %s", self.hostname)
        try:
            self._netmiko_close()
        except Exception:
            pass
        self.device = self._netmiko_open(
            "hp_comware", netmiko_optional_args=self.netmiko_optional_args
        )
        self._command_cache = {}
        # Disable terminal paging (same as open())
        try:
            self.device.send_command("screen-length disable", read_timeout=10)
        except Exception:
            logger.debug("screen-length disable failed (may not be supported)")
        if self.force_english:
            self._force_english_output()
        logger.info("Reconnected to %s", self.hostname)

    def is_alive(self):
        """Check if the connection to the device is alive.

        When ``is_alive_active_probe`` is enabled (via optional_args),
        sends a lightweight command (``display clock``) to verify the
        connection is responsive.  Otherwise delegates to Netmiko's
        passive ``is_alive()`` check.
        """
        if self.device is None:
            result = {"is_alive": False}
        elif self._is_alive_active_probe:
            try:
                output = self.device.send_command("display clock", read_timeout=10)
                result = {"is_alive": bool(output and output.strip())}
            except Exception:
                result = {"is_alive": False}
        else:
            result = {"is_alive": self.device.is_alive()}
        logger.debug("is_alive: %s", result)
        return result

    def _force_english_output(self):
        """Send terminal language to force English CLI output."""
        try:
            self.device.send_command("terminal language", read_timeout=5)
            logger.debug("Set terminal language to English")
        except Exception:
            logger.warning("Failed to set terminal language to English")

    def _discover_profile(self):
        """Build device profile from display version output.

        Uses ``send_command_timing`` directly because chassis/frame devices
        (e.g. S12504G) produce extremely long output that causes prompt-based
        ``send_command`` to either truncate the output or return empty due to
        stale buffer data.  ``send_command_timing`` reads until the output
        stabilises, which works reliably for all device form factors.

        After the timing-based read the session prompt is re-synced via
        ``find_prompt`` so that subsequent ``send_command`` calls work.
        """
        try:
            raw_output = self.device.send_command_timing(
                "display version", read_timeout=120, delay_factor=4
            )
            # Re-sync the session prompt after timing-based read
            self._resync_prompt()
            if not raw_output:
                logger.warning("display version returned empty output")
                return
            # Parse structured data from the raw output we already have
            try:
                structured = textfsm_extractor(self, "display_version", raw_output)
            except Exception:
                structured = []
            model = ""
            os_version = ""
            if isinstance(structured, list) and len(structured) >= 1:
                # Chassis devices may produce multiple records; use the last
                # one which contains the actual system version header.
                info = structured[-1]
                model = info.get("model", "")
                os_version = info.get("os_version", "")
            # Fallback: extract model and version from raw output via regex
            # when TextFSM fails (e.g. unexpected output format)
            if not model:
                m = re.search(
                    r"(?:H3C|h3c)\s+(\S+)\s+uptime\s+is", raw_output
                )
                if m:
                    model = m.group(1)
            if not os_version:
                m = re.search(
                    r"Comware\s+Software.*?Version\s+[\d.]+,\s*(Release\s+\S+)",
                    raw_output, re.IGNORECASE,
                )
                if m:
                    os_version = m.group(1)
                else:
                    m = re.search(r"Release\s+(\S+)", raw_output)
                    if m:
                        os_version = "Release " + m.group(1)
            self.profile = build_device_profile(
                model=model,
                os_version=os_version,
                version_output=raw_output,
            )
            if self.profile.major_version is not None:
                logger.info("Device profile: %s", self.profile)
            else:
                logger.warning("Could not determine device profile from display version")
        except Exception as e:
            logger.warning("Profile discovery failed: %s", e)

    def _get_command(self, key: str) -> str:
        """Resolve a command string from the registry for the current profile."""
        if self.profile is not None and self.profile.major_version is not None:
            try:
                spec = self.command_registry.resolve(key, self.profile)
                return spec.command
            except UnsupportedCommandError:
                pass
        specs = self.command_registry.get(key)
        if specs:
            return specs[0].command
        raise UnsupportedCommandError(f"No command spec for key={key!r}")

    def _get_structured_output(self, command: str, template_name: str = None):
        """
        Wrapper for `napalm.base.helpers.textfsm_extractor()`.
        Results are cached per session to avoid duplicate commands.
        """
        if template_name is None:
            template_name = "_".join(command.split())
        cache_key = (command, template_name)
        if cache_key in self._command_cache:
            logger.debug("Cache hit for command=%s template=%s", command, template_name)
            return self._command_cache[cache_key]
        raw_output = self.send_command(command)
        try:
            result = textfsm_extractor(self, template_name, raw_output)
        except Exception as e:
            logger.error("TextFSM parse failed for %s: %s", template_name, e)
            raise ComwareParserError(
                f"Failed to parse output of '{command}' with template '{template_name}': {e}"
            ) from e
        if not result:
            logger.warning("Empty TextFSM result for command=%s template=%s", command, template_name)
            # Do NOT cache empty results: a transient failure (network glitch,
            # stale buffer) should not poison the cache for the entire session.
        else:
            logger.debug("Parsed %d records from command=%s template=%s", len(result), command, template_name)
            self._command_cache[cache_key] = result
        return result

    def _raise_not_implemented(self, method_name: str):
        raise NotImplementedError(
            "%s is not implemented for this H3C Comware driver yet. "
            "See docs/getters-support-matrix.md for the current support status." % method_name
        )

    @staticmethod
    def _select_vlan_name(vlan_name: str, vlan_desc: str) -> str:
        """Select the best display name for a VLAN.

        H3C default: name="VLAN 0001", description="" or same as name.
        If description is non-empty and differs from the auto-generated name,
        prefer it. Otherwise use name.
        """
        if not vlan_desc:
            return vlan_name
        if vlan_desc == vlan_name:
            return vlan_name
        # Both non-empty and different: prefer description if name looks auto-generated
        if re.match(r"^VLAN\s+\d+$", vlan_name, re.IGNORECASE) and not re.match(
            r"^VLAN\s+\d+$", vlan_desc, re.IGNORECASE
        ):
            return vlan_desc
        return vlan_name

    def get_facts(self):
        vendor = "Comware"
        uptime = -1
        serial_number, fqdn, os_version, hostname, model = ("Unknown",) * 5
        interface_list = []

        try:
            # uptime, vendor, model
            cmd_sys_info = self._get_command("facts.version")
            structured_sys_info = self._get_structured_output(cmd_sys_info)
            if isinstance(structured_sys_info, list) and len(structured_sys_info) == 1:
                structured_sys_info = structured_sys_info[0]
                uptime_str = structured_sys_info.get("uptime", "")
                vendor = structured_sys_info.get("vendor", "Comware")
                model = structured_sys_info.get("model", "Unknown")
                os_version = structured_sys_info.get("os_version", "Unknown")
                if uptime_str:
                    uptime = parse_time(uptime_str)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_facts (version info): %s", e)

        # hostname
        try:
            prompt = self.device.find_prompt()
            hostname = prompt[1:-1] if len(prompt) > 2 else prompt
        except Exception as e:
            logger.error("Error in get_facts (hostname): %s", e)

        # interfaces
        try:
            structured_int_info = self._get_structured_output(self._get_command("facts.interfaces"))
            for interface in structured_int_info:
                interface_list.append(interface.get("interface"))
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_facts (interfaces): %s", e)

        # serial number
        try:
            cmd_sn = self._get_command("facts.serial")
            structured_sn = self._get_structured_output(cmd_sn)
            if isinstance(structured_sn, list) and len(structured_sn) > 0:
                chassis_list = []
                slot_list = []
                for sn in structured_sn:
                    if sn.get("slot_type") == "Chassis":
                        chassis_sn = sn.get("serial_number", "")
                        if chassis_sn != "":
                            chassis_list.append(chassis_sn)
                    if sn.get("slot_type") == "Slot":
                        slot_sn = sn.get("serial_number", "")
                        if slot_sn != "":
                            slot_list.append(slot_sn)

                if len(chassis_list) > 0:
                    serial_number = ",".join(chassis_list)
                elif len(slot_list) > 0:
                    serial_number = ",".join(slot_list)
                else:
                    serial_number = "Unknown"
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_facts (serial number): %s", e)

        return {
            "uptime": uptime,
            "vendor": vendor,
            "os_version": os_version,
            "serial_number": serial_number,
            "model": model,
            "hostname": hostname,
            "fqdn": fqdn,
            "interface_list": interface_list,
        }

    def get_interfaces(self):
        interface_dict = {}

        try:
            structured_int_info = self._get_structured_output(self._get_command("interfaces"))

            for interface in structured_int_info:
                # Physical state:
                #   - Administratively DOWN
                #   - DOWN
                #   - UP
                link_status = interface.get("link_status", "")
                is_enabled = bool(link_status and "up" in link_status.lower())
                # Protocol state:
                #  - UP
                #  - UP (spoofing)
                #  - DOWN
                #  - DOWN(other protocol):such as DOWN(DLDP)、DOWN(LAGG) ...
                protocol_status = interface.get("protocol_status", "")
                is_up = bool(protocol_status and "up" in protocol_status.lower())

                description = interface.get("description", "")
                speed = interface.get("bandwidth", "")
                mtu = interface.get("mtu", "")
                mac_address = interface.get("mac_address", "")
                last_flapped = interface.get("last_flapping", "")

                # Never flapping: 0
                # No flapping data: -1
                # Last flapping: int(seconds)
                if last_flapped and "never" in last_flapped.lower():
                    last_flapped = 0
                else:
                    last_flapped = parse_null(last_flapped, -1, parse_time)

                interface_dict[interface.get("interface")] = {
                    "is_enabled": is_enabled,
                    "is_up": is_up,
                    "description": description,
                    "speed": parse_null(speed, -1, int),
                    "mtu": parse_null(mtu, -1, int),
                    "mac_address": parse_null(mac_address, "unknown", mac),
                    "last_flapped": last_flapped,
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_interfaces: %s", e)

        return interface_dict

    def get_lldp_neighbors(self):
        lldp = {}

        try:
            command = self._get_command("lldp.neighbors")
            structured_output = self._get_structured_output(command)
            for lldp_entry in structured_output:
                local_interface = lldp_entry.get("local_interface", "")
                remote_system_name = lldp_entry.get("remote_system_name", "")
                remote_port = lldp_entry.get("remote_port", "")
                if lldp.get(local_interface) is None:
                    lldp[local_interface] = [{
                        "hostname": remote_system_name,
                        "port": remote_port
                    }]
                else:
                    lldp[local_interface].append({
                        "hostname": remote_system_name,
                        "port": remote_port
                    })
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_lldp_neighbors: %s", e)

        return lldp

    def get_bgp_neighbors(self):
        """Return BGP neighbor summary per VRF.

        Uses ``display bgp`` for router_id and ``display bgp peer ipv4``
        for peer state and prefix counts.
        """
        result = {}

        try:
            # Get router_id from display bgp
            router_id = ""
            try:
                summary_cmd = self._get_command("bgp.summary")
                summary_output = self._get_structured_output(
                    summary_cmd, "display_bgp"
                )
                if summary_output:
                    router_id = summary_output[0].get("router_id", "")
            except (UnsupportedCommandError, ComwareParserError):
                logger.warning("Could not get BGP router_id from display bgp")

            # Get peer list
            command = self._get_command("bgp.peer")
            structured_output = self._get_structured_output(command)

            peers = {}
            for peer_entry in structured_output:
                if not router_id:
                    router_id = peer_entry.get("router_id", "")

                peer_ip = peer_entry.get("peer", "")
                if not peer_ip:
                    continue

                state = peer_entry.get("state", "")
                is_up = state.lower() == "established"
                local_as = int(parse_null(peer_entry.get("local_as", 0), 0))
                remote_as = int(parse_null(peer_entry.get("remote_as", 0), 0))

                received_prefixes = int(parse_null(peer_entry.get("pref_rcv", 0), 0))
                accepted_prefixes = int(parse_null(peer_entry.get("accepted", 0), 0))
                sent_prefixes = int(parse_null(peer_entry.get("upstream", 0), 0))

                peers[peer_ip] = {
                    "local_as": local_as,
                    "remote_as": remote_as,
                    "remote_id": "",
                    "is_up": is_up,
                    "is_enabled": True,
                    "description": "",
                    "uptime": -1,
                    "address_family": {
                        "ipv4": {
                            "received_prefixes": received_prefixes,
                            "accepted_prefixes": accepted_prefixes,
                            "sent_prefixes": sent_prefixes,
                        }
                    },
                }

            result["global"] = {
                "router_id": router_id,
                "peers": peers,
            }

        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_bgp_neighbors: %s", e)

        return result

    def _get_memory(self, verbose=True):

        memory = {}

        try:
            command = self._get_command("environment.memory")
            structured_output = self._get_structured_output(command)
            for mem_entry in structured_output:
                chassis = mem_entry.get("chassis", "")
                slot = mem_entry.get("slot", "")
                total = mem_entry.get("total", "0")
                used = mem_entry.get("used", "0")
                free = mem_entry.get("free", "0")
                free_ratio = mem_entry.get("free_ratio", "0")

                if chassis != "":
                    memory_key = "chassis %s slot %s" % (chassis, slot)
                elif chassis == "" and slot != "":
                    memory_key = "slot %s" % (slot)
                else:
                    continue

                memory[memory_key] = {
                    "total_ram": int(total),
                    "used_ram": int(used),
                    "available_ram": int(free),
                    "free_ratio": float(free_ratio),
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in _get_memory: %s", e)

        if verbose:
            return memory
        else:
            # 为了适配 napalm api（只支持回显一条信息），如果有多个板卡的话，只返回使用空间最多的
            # return info of the slot with max memory usage if device has more than one slot.
            _mem = {}
            if memory:
                _ = get_value_from_list_of_dict(
                    list(memory.values()), "free_ratio", min)
                _mem["used_ram"] = _.get("used_ram")
                _mem["available_ram"] = _.get("available_ram")
            return _mem

    def _get_power(self, verbose=True):
        # 盒式设备只有 Slot，框式设备只有 Chassis
        power = {}

        try:
            command = self._get_command("environment.power")
            structured_output = self._get_structured_output(command)
            for power_entry in structured_output:
                chassis = power_entry.get("chassis", "")
                slot = power_entry.get("slot", "")
                power_id = power_entry.get("power_id", "")
                status = power_entry.get("status", "")
                output = power_entry.get("power", "")

                if not verbose:
                    status = status.lower() == "normal" if status else False

                if slot != "":
                    power_key = "Slot %s Power %s" % (slot, power_id)
                elif chassis != "":
                    power_key = "Chassis %s Power %s" % (chassis, power_id)
                else:
                    power_key = "Power %s" % (power_id)

                power[power_key] = {
                    "status": status,
                    "capacity": -1,
                    "output": output
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in _get_power: %s", e)

        return power

    def _get_cpu(self, verbose=True):
        cpu = {}

        try:
            command = self._get_command("environment.cpu")
            structured_output = self._get_structured_output(command)
            for cpu_entry in structured_output:
                chassis = cpu_entry.get("chassis", "")
                slot = cpu_entry.get("slot", "")
                cpu_id = cpu_entry.get("cpu_id", "")
                five_sec = cpu_entry.get("five_sec", "0")
                one_min = cpu_entry.get("one_min", "0")
                five_min = cpu_entry.get("five_min", "0")

                if chassis != "":
                    cpu_key = "Chassis %s Slot %s cpu %s" % (chassis, slot, cpu_id)
                elif chassis == "" and slot != "":
                    cpu_key = "Slot %s cpu %s" % (slot, cpu_id)
                else:
                    cpu_key = "cpu %s" % (cpu_id)

                if verbose:
                    cpu[cpu_key] = {
                        "five_sec": float(five_sec),
                        "one_min": float(one_min),
                        "five_min": float(five_min),
                    }
                else:
                    cpu[cpu_key] = {
                        r"%usage": float(max([float(five_sec), float(one_min), float(five_min)])),
                    }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in _get_cpu: %s", e)

        return cpu

    def _get_fan(self):
        fans = {}

        try:
            command = self._get_command("environment.fan")
            structured_output = self._get_structured_output(command)
            for fan_entry in structured_output:
                chassis = fan_entry.get("chassis", "")
                slot = fan_entry.get("slot", "")
                fan_id = fan_entry.get("fan_id", "")
                status = fan_entry.get("status", "")
                status = status.lower() == "normal" if status else False
                if slot != "":
                    fan_key = "Slot %s Fan %s" % (slot, fan_id)
                elif chassis != "":
                    fan_key = "Chassis %s Fan %s" % (chassis, fan_id)
                else:
                    fan_key = "Fan %s" % (fan_id)
                fans[fan_key] = {
                    "status": status
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in _get_fan: %s", e)

        return fans

    def _get_temperature(self):
        temperature = {}

        try:
            command = self._get_command("environment.temperature")
            structured_output = self._get_structured_output(command)
            for temp_entry in structured_output:
                chassis = temp_entry.get("chassis", "")
                slot = temp_entry.get("slot", "")
                sensor = temp_entry.get("sensor", "")
                temp = temp_entry.get("temperature", "0")
                alert = temp_entry.get("alert", "0")
                critical = temp_entry.get("critical", "0")
                temp_val = float(temp) if temp else 0
                alert_val = float(alert) if alert else 0
                critical_val = float(critical) if critical else 0
                # A threshold of 0 means "not configured"; do not trigger
                # false alerts when the threshold is unset.
                is_alert = temp_val >= alert_val if alert_val > 0 else False
                is_critical = temp_val >= critical_val if critical_val > 0 else False

                if chassis != "":
                    temp_key = "Chassis %s Slot %s Sensor %s" % (
                        chassis, slot, sensor)
                else:
                    temp_key = "Slot %s Sensor %s" % (slot, sensor)
                temperature[temp_key] = {
                    "temperature": float(temp),
                    "is_alert": is_alert,
                    "is_critical": is_critical,
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in _get_temperature: %s", e)

        return temperature

    def get_environment(self):
        environment = {}

        cpu = self._get_cpu(verbose=False)
        environment["cpu"] = cpu

        memory = self._get_memory(verbose=False)
        environment["memory"] = memory

        power = self._get_power(verbose=False)
        environment["power"] = power

        fans = self._get_fan()
        environment["fans"] = fans

        temperature = self._get_temperature()
        environment["temperature"] = temperature

        return environment

    def get_interfaces_counters(self):
        """Return interface counters and errors.

        Parses ``display interface`` output using TextFSM.
        The template produces one record per line; this method merges
        them into per-interface counter dicts keyed by interface name.
        Interfaces without counter sections (VLAN, Loopback, NULL) are
        not included.
        """
        counters = {}
        try:
            command = self._get_command("interfaces.counters")
            structured_output = self._get_structured_output(
                command, "display_interface_counters"
            )
            # TextFSM produces one record per line; merge by tracking
            # current interface and Input/Output section
            current_iface = ""
            current_section = ""
            for entry in structured_output:
                iface = entry.get("interface", "")
                if iface:
                    current_iface = iface
                    if current_iface not in counters:
                        counters[current_iface] = {
                            "tx_errors": 0, "rx_errors": 0,
                            "tx_discards": 0, "rx_discards": 0,
                            "tx_octets": 0, "rx_octets": 0,
                            "tx_unicast_packets": 0, "rx_unicast_packets": 0,
                            "tx_multicast_packets": 0, "rx_multicast_packets": 0,
                            "tx_broadcast_packets": 0, "rx_broadcast_packets": 0,
                        }
                    continue

                section = entry.get("section", "")
                if section:
                    current_section = section.lower()

                if not current_iface or not current_section:
                    continue

                prefix = "rx_" if current_section == "input" else "tx_"
                bytes_val = entry.get("bytes", "")
                if bytes_val:
                    counters[current_iface][prefix + "octets"] = int(bytes_val)
                unicasts = entry.get("unicasts", "")
                if unicasts:
                    counters[current_iface][prefix + "unicast_packets"] = int(unicasts)
                multicasts = entry.get("multicasts", "")
                if multicasts:
                    counters[current_iface][prefix + "multicast_packets"] = int(multicasts)
                broadcasts = entry.get("broadcasts", "")
                if broadcasts:
                    counters[current_iface][prefix + "broadcast_packets"] = int(broadcasts)
                errors = entry.get("errors", "")
                if errors:
                    counters[current_iface][prefix + "errors"] = int(errors)
                discards = entry.get("discards", "")
                if discards:
                    counters[current_iface][prefix + "discards"] = int(discards)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_interfaces_counters: %s", e)

        return counters

    def get_lldp_neighbors_detail(self, interface: str = ""):
        lldp = {}
        # `parent_interface` is not supported
        parent_interface = ""

        try:
            if interface:
                command = "display lldp neighbor-information interface %s verbose" % (
                    interface)
            else:
                command = self._get_command("lldp.neighbors.detail")

            structured_output = self._get_structured_output(
                command, "display_lldp_neighbor-information_verbose")

            for lldp_entry in structured_output:
                local_interface = lldp_entry.get("local_interface", "")
                remote_port = lldp_entry.get("remote_port", "")
                remote_port_description = lldp_entry.get("remote_port_desc", "")
                remote_chassis_id = lldp_entry.get("remote_chassis_id", "")
                remote_system_name = lldp_entry.get("remote_system_name", "")
                remote_system_description = lldp_entry.get("remote_system_desc", [])
                remote_system_capab = lldp_entry.get("remote_system_capab", "")
                remote_system_enabled_capab = lldp_entry.get("remote_system_enabled_capab", "")

                _ = {
                    "parent_interface": parent_interface,
                    "remote_port": remote_port,
                    "remote_port_description": remote_port_description,
                    "remote_chassis_id": remote_chassis_id,
                    "remote_system_name": remote_system_name,
                    "remote_system_description": "".join(remote_system_description) if isinstance(remote_system_description, list) else str(remote_system_description),
                    "remote_system_capab": [i.strip() for i in remote_system_capab.split(",")] if remote_system_capab else [],
                    "remote_system_enabled_capab": [i.strip() for i in remote_system_enabled_capab.split(",")] if remote_system_enabled_capab else [],
                }
                if lldp.get(local_interface) is None:
                    lldp[local_interface] = [_]
                else:
                    lldp[local_interface].append(_)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_lldp_neighbors_detail: %s", e)

        return lldp

    def cli(self, commands: List):

        cli_output = dict()

        if type(commands) is not list:
            raise TypeError("Please enter a valid list of commands!")

        for command in commands:
            output = self.device.send_command(command)
            cli_output.setdefault(command, {})
            cli_output[command] = output

        return cli_output

    def get_arp_table(self, vrf: str = ""):
        arp_table = []

        try:
            base_cmd = self._get_command("arp")
            command = base_cmd if not vrf else "display arp vpn-instance %s" % (vrf)
            structured_output = self._get_structured_output(command, "display_arp")
            for arp_entry in structured_output:
                interface = arp_entry.get("interface", "")
                mac_address = arp_entry.get("mac_address", "")
                ip = arp_entry.get("ip_address", "")
                age = arp_entry.get("aging", "0")
                entry = {
                    'interface': canonical_interface_name_comware(interface),
                    'mac': mac(mac_address),
                    'ip': ip,
                    'age': float(age),
                }
                arp_table.append(entry)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_arp_table: %s", e)

        return arp_table

    def get_interfaces_ip(self):
        """Return IP addresses (IPv4 and IPv6) configured on interfaces.

        IPv4 data from ``display ip interface``, IPv6 data from
        ``display ipv6 interface``. Each address family is parsed
        independently so one failure does not affect the other.
        """
        interfaces = {}

        try:
            command = self._get_command("interfaces.ipv4")
            structured_output = self._get_structured_output(command)
            for iface_entry in structured_output:
                interface = canonical_interface_name_comware(
                    iface_entry.get("interface", "")
                )
                ip_list = iface_entry.get("ip_address", [])
                ipv4 = {}
                if ip_list:
                    for ip in ip_list:
                        parts = ip.split("/")
                        if len(parts) == 2:
                            ipv4[parts[0]] = {"prefix_length": int(parts[1])}
                if ipv4:
                    interfaces.setdefault(interface, {})["ipv4"] = ipv4
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_interfaces_ip (IPv4): %s", e)

        try:
            command = self._get_command("interfaces.ipv6")
            structured_output = self._get_structured_output(command)
            for iface_entry in structured_output:
                interface = canonical_interface_name_comware(
                    iface_entry.get("interface", "")
                )
                ipv6 = {}
                # Global unicast addresses
                global_addrs = iface_entry.get("global_address", [])
                global_prefixes = iface_entry.get("global_prefix_length", [])
                for addr, prefix in zip(global_addrs, global_prefixes):
                    ipv6[addr] = {"prefix_length": int(prefix)}
                # Link-local address (fixed /10 prefix)
                link_local = iface_entry.get("link_local", "")
                if link_local:
                    ipv6[link_local] = {"prefix_length": 10}
                if ipv6:
                    interfaces.setdefault(interface, {})["ipv6"] = ipv6
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_interfaces_ip (IPv6): %s", e)

        return interfaces

    def get_mac_address_move_table(self):
        mac_address_move_table = []

        try:
            command = self._get_command("mac.move")
            structured_output = self._get_structured_output(command)
            for mac_move_entry in structured_output:
                mac_address = mac_move_entry.get("mac_address", "")
                vlan = mac_move_entry.get("vlan", "0")
                current_port = mac_move_entry.get("current_port", "")
                source_port = mac_move_entry.get("source_port", "")
                last_move = mac_move_entry.get("last_move", "")
                moves = mac_move_entry.get("times", "-1")
                entry = {
                    "mac": mac(mac_address),
                    "vlan": int(vlan),
                    "current_port": canonical_interface_name_comware(current_port),
                    "source_port": canonical_interface_name_comware(source_port),
                    "last_move": last_move,
                    "moves": int(moves),
                }
                mac_address_move_table.append(entry)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_mac_address_move_table: %s", e)

        return mac_address_move_table

    def get_mac_address_table(self):
        mac_address_table = []

        try:
            command = self._get_command("mac.table")
            structured_output = self._get_structured_output(command)
            mac_address_move_table = self.get_mac_address_move_table()

            # Build MAC -> move info dict for O(1) lookup
            move_lookup = {}
            for mac_move in mac_address_move_table:
                move_lookup[mac_move.get("mac_address")] = mac_move

            for mac_entry in structured_output:
                mac_address = mac_entry.get("mac_address", "")
                vlan = mac_entry.get("vlan", "0")
                state = mac_entry.get("state", "")
                interface = mac_entry.get("interface", "")
                entry = {
                    "mac": mac(mac_address),
                    "interface": canonical_interface_name_comware(interface),
                    "vlan": int(vlan),
                    "static": "static" in state.lower() if state else False,
                    "state": state,
                    "active": True,
                }
                # O(1) lookup
                move_info = move_lookup.get(mac_address)
                if move_info:
                    try:
                        entry["last_move"] = strptime(move_info.get("last_move"))
                    except (ValueError, TypeError):
                        entry["last_move"] = -1.0
                    entry["moves"] = int(move_info.get("times", -1))
                else:
                    entry["last_move"] = -1.0
                    entry["moves"] = -1
                mac_address_table.append(entry)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_mac_address_table: %s", e)

        return mac_address_table

    def get_route_to(self, destination="", protocol="", longer=False):
        """Return route entries from the H3C Comware routing table.

        When ``destination`` is provided, uses verbose output for richer fields
        (age, state). Otherwise uses bulk non-verbose output where age defaults
        to -1 and inactive_reason defaults to "".
        """
        routes = defaultdict(list)

        try:
            if destination:
                cmd_template = self._get_command("route.table.verbose")
                command = cmd_template.format(destination)
                structured_output = self._get_structured_output(
                    command, "display_ip_routing-table_verbose"
                )
                for entry in structured_output:
                    proto = entry.get("protocol", "").lower()
                    if protocol and proto != protocol.lower():
                        continue
                    state = entry.get("state", "")
                    is_active = "active" in state.lower() if state else True
                    age_str = entry.get("age", "")
                    age = parse_time(age_str) if age_str else -1
                    route_entry = {
                        "protocol": proto,
                        "current_active": is_active,
                        "last_active": is_active,
                        "age": age,
                        "next_hop": entry.get("next_hop", ""),
                        "outgoing_interface": entry.get("interface", ""),
                        "selected_next_hop": is_active,
                        "preference": int(parse_null(entry.get("preference", 0), 0)),
                        "inactive_reason": "" if is_active else "Inactive",
                        "routing_table": "default",
                        "protocol_attributes": {},
                    }
                    dest = entry.get("destination", destination)
                    routes[dest].append(route_entry)
            else:
                command = self._get_command("route.table")
                structured_output = self._get_structured_output(command)
                for entry in structured_output:
                    proto = entry.get("protocol", "").lower()
                    if protocol and proto != protocol.lower():
                        continue
                    route_entry = {
                        "protocol": proto,
                        "current_active": True,
                        "last_active": True,
                        "age": -1,
                        "next_hop": entry.get("next_hop", ""),
                        "outgoing_interface": entry.get("interface", ""),
                        "selected_next_hop": True,
                        "preference": int(parse_null(entry.get("preference", 0), 0)),
                        "inactive_reason": "",
                        "routing_table": "default",
                        "protocol_attributes": {},
                    }
                    dest = entry.get("destination", "")
                    if dest:
                        routes[dest].append(route_entry)

        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_route_to: %s", e)

        return dict(routes)

    def get_config(
        self,
        retrieve: str = "all",
        full: bool = False,
        sanitized: bool = False,
        format: str = "text",
    ) -> models.ConfigDict:
        """Return the running and/or startup configuration.

        Args:
            retrieve: Which configuration to return ("running", "startup", or "all").
            full: If True, retrieve the full configuration. On H3C Comware,
                ``display current-configuration`` already returns the full
                configuration by default, so this parameter is a no-op.
            sanitized: If True, remove sensitive data (passwords, keys, SNMP
                community strings) from the returned configuration using
                H3C Comware-specific filter patterns.
            format: The configuration format. H3C Comware only supports "text"
                format. Other values are accepted but have no effect.

        Returns:
            A dictionary with keys "running", "startup", and "candidate".
            The "candidate" key is always an empty string because H3C Comware
            does not have a native candidate configuration store.
        """
        configs: models.ConfigDict = {"startup": "", "running": "", "candidate": ""}

        # full=True is a no-op on Comware: display current-configuration
        # already shows the complete running configuration.
        if full:
            logger.debug("get_config(full=True): Comware always returns full config, no-op")

        if retrieve.lower() in ("running", "all"):
            command = self._get_command("config.running")
            configs["running"] = self.send_command(command, read_timeout=120)
        if retrieve.lower() in ("startup", "all"):
            command = self._get_command("config.startup")
            configs["startup"] = self.send_command(command, read_timeout=120)

        if sanitized:
            configs = sanitize_configs(configs, COMWARE_SANITIZE_FILTERS)

        return configs

    def get_network_instances(self, name: str = ""):
        """Return VRF/network instance information.

        Always includes the default instance. VPN instances are discovered
        from ``display ip vpn-instance`` and enriched with interface data
        from ``display ip vpn-instance instance-name <name>``.
        """
        instances = {}

        try:
            # Always add the default instance
            instances["default"] = {
                "name": "default",
                "type": "DEFAULT_INSTANCE",
                "state": {"route_distinguisher": None},
                "interfaces": {"interface": {}},
            }

            # Populate default instance interfaces from get_interfaces_ip
            try:
                interfaces_ip = self.get_interfaces_ip()
                default_ifaces = {iface: {} for iface in interfaces_ip}
                instances["default"]["interfaces"]["interface"] = default_ifaces
            except Exception:
                pass

            # Get VPN instances
            command = self._get_command("vpn.instance")
            structured_output = self._get_structured_output(command)

            for vrf_entry in structured_output:
                vrf_name = vrf_entry.get("vpn_instance_name", "")
                if not vrf_name:
                    continue
                if name and vrf_name != name:
                    continue

                rd = vrf_entry.get("rd", "")
                if rd and rd.lower() in ("<not set>", "none", "-"):
                    rd = None

                vrf_interfaces = {"interface": {}}

                # Get per-VRF detail for interface list
                try:
                    detail_cmd_template = self._get_command("vpn.instance.detail")
                    detail_cmd = detail_cmd_template.format(vrf_name)
                    detail_output = self._get_structured_output(
                        detail_cmd, "display_ip_vpn-instance_instance-name"
                    )
                    if detail_output:
                        iface_list = detail_output[0].get("interfaces", [])
                        iface_dict = {iface: {} for iface in iface_list}
                        vrf_interfaces["interface"] = iface_dict
                except (UnsupportedCommandError, ComwareParserError) as e:
                    logger.warning(
                        "Could not get VRF detail for %s: %s", vrf_name, e
                    )

                instances[vrf_name] = {
                    "name": vrf_name,
                    "type": "L3VRF",
                    "state": {"route_distinguisher": rd},
                    "interfaces": vrf_interfaces,
                }

        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_network_instances: %s", e)

        return instances

    def get_bgp_config(self, group="", neighbor=""):
        """Return BGP configuration from the device.

        Parses ``display current-configuration configuration bgp`` output
        using multi-pass regex to extract peer groups and individual peers.
        """
        bgp_config = {}
        try:
            command = self._get_command("bgp.config")
            config_output = self.send_command(command)
            if not config_output.strip():
                return bgp_config

            # Parse BGP AS number
            bgp_match = re.search(r"bgp\s+(\d+)", config_output)
            if not bgp_match:
                return bgp_config
            local_as = int(bgp_match.group(1))

            # Parse peer groups
            groups = {}
            group_re = re.compile(r"^\s*group\s+(\S+)\s+(internal|external)", re.MULTILINE)
            for g_match in group_re.finditer(config_output):
                g_name = g_match.group(1)
                g_type = g_match.group(2)
                groups[g_name] = {
                    "type": g_type,
                    "description": "",
                    "apply_groups": [],
                    "multihop_ttl": 0,
                    "multipath": False,
                    "local_address": "",
                    "local_as": local_as,
                    "remote_as": 0,
                    "import_policy": "",
                    "export_policy": "",
                    "remove_private_as": False,
                    "prefix_limit": {},
                    "neighbors": {},
                }

            # Parse group-level peer attributes
            for m in re.finditer(r"^\s*peer\s+(\S+)\s+as-number\s+(\d+)", config_output, re.MULTILINE):
                name, asn = m.group(1), int(m.group(2))
                if name in groups:
                    groups[name]["remote_as"] = asn

            for m in re.finditer(r"^\s*peer\s+(\S+)\s+description\s+\"?([^\"]+)\"?", config_output, re.MULTILINE):
                name, desc = m.group(1), m.group(2).strip()
                if name in groups:
                    groups[name]["description"] = desc

            for m in re.finditer(
                r"^\s*peer\s+(\S+)\s+(?:import-route-policy|route-policy)\s+(\S+)\s+(import|export)",
                config_output, re.MULTILINE,
            ):
                name, policy, direction = m.group(1), m.group(2), m.group(3)
                if name in groups:
                    if direction == "import":
                        groups[name]["import_policy"] = policy
                    elif direction == "export":
                        groups[name]["export_policy"] = policy

            # Parse individual peers
            peer_data = {}
            for m in re.finditer(r"^\s*peer\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+(.*)", config_output, re.MULTILINE):
                peer_ip, attr, value = m.group(1), m.group(2), m.group(3).strip()
                if peer_ip not in peer_data:
                    peer_data[peer_ip] = {
                        "description": "",
                        "import_policy": "",
                        "export_policy": "",
                        "local_address": "",
                        "authentication_key": "",
                        "nhs": False,
                        "route_reflector_client": False,
                        "local_as": local_as,
                        "remote_as": 0,
                        "prefix_limit": {},
                        "_group": "",
                    }
                if attr == "as-number":
                    peer_data[peer_ip]["remote_as"] = int(value)
                elif attr == "group":
                    peer_data[peer_ip]["_group"] = value
                elif attr == "description":
                    peer_data[peer_ip]["description"] = value.strip('"')
                elif attr in ("import-route-policy", "route-policy") and "import" in value:
                    peer_data[peer_ip]["import_policy"] = value.split()[0]
                elif attr in ("export-route-policy", "route-policy") and "export" in value:
                    peer_data[peer_ip]["export_policy"] = value.split()[0]
                elif attr == "password":
                    peer_data[peer_ip]["authentication_key"] = value

            # Assign peers to groups
            for peer_ip, pdata in peer_data.items():
                group_name = pdata.pop("_group", "")
                if group_name and group_name in groups:
                    groups[group_name]["neighbors"][peer_ip] = pdata
                else:
                    groups[peer_ip] = {
                        "type": "",
                        "description": pdata.get("description", ""),
                        "apply_groups": [],
                        "multihop_ttl": 0,
                        "multipath": False,
                        "local_address": pdata.get("local_address", ""),
                        "local_as": pdata.get("local_as", local_as),
                        "remote_as": pdata.get("remote_as", 0),
                        "import_policy": pdata.get("import_policy", ""),
                        "export_policy": pdata.get("export_policy", ""),
                        "remove_private_as": False,
                        "prefix_limit": {},
                        "neighbors": {peer_ip: pdata},
                    }

            # Add default group for ungrouped peers
            if "_" not in groups:
                groups["_"] = {
                    "type": "",
                    "description": "",
                    "apply_groups": [],
                    "multihop_ttl": 0,
                    "multipath": False,
                    "local_address": "",
                    "local_as": local_as,
                    "remote_as": 0,
                    "import_policy": "",
                    "export_policy": "",
                    "remove_private_as": False,
                    "prefix_limit": {},
                    "neighbors": {},
                }

            bgp_config = groups
            if group:
                bgp_config = {k: v for k, v in groups.items() if k == group}
            if neighbor:
                bgp_config = {
                    k: {**v, "neighbors": {n: nv for n, nv in v["neighbors"].items() if n == neighbor}}
                    for k, v in bgp_config.items()
                    if neighbor in v.get("neighbors", {})
                }
        except Exception as e:
            logger.error("Error in get_bgp_config: %s", e)

        return bgp_config

    def get_bgp_neighbors_detail(self, neighbor_address=""):
        """Return detailed BGP neighbor information.

        WARNING: This getter iterates each BGP peer with a separate
        ``display bgp peer <ip> verbose`` command, which is expensive
        on devices with many peers.
        """
        result = {}

        try:
            # Step 1: Get peer list from summary
            peer_cmd = self._get_command("bgp.peer")
            peer_output = self._get_structured_output(peer_cmd)

            # Step 2: Get router_id
            router_id = ""
            try:
                summary_cmd = self._get_command("bgp.summary")
                summary_output = self._get_structured_output(
                    summary_cmd, "display_bgp"
                )
                if summary_output:
                    router_id = summary_output[0].get("router_id", "")
            except (UnsupportedCommandError, ComwareParserError):
                pass

            # Step 3: Iterate peers for verbose detail
            verbose_cmd_template = self._get_command("bgp.peer.verbose")

            for peer_entry in peer_output:
                peer_ip = peer_entry.get("peer", "")
                if not peer_ip:
                    continue
                if neighbor_address and peer_ip != neighbor_address:
                    continue

                if not router_id:
                    router_id = peer_entry.get("router_id", "")

                remote_as = int(parse_null(peer_entry.get("remote_as", 0), 0))
                local_as = int(parse_null(peer_entry.get("local_as", 0), 0))

                # Get verbose detail for this peer
                try:
                    verbose_cmd = verbose_cmd_template.format(peer_ip)
                    verbose_output = self._get_structured_output(
                        verbose_cmd, "display_bgp_peer_verbose"
                    )
                except (UnsupportedCommandError, ComwareParserError) as e:
                    logger.warning(
                        "Could not get verbose detail for peer %s: %s",
                        peer_ip, e,
                    )
                    verbose_output = []

                if verbose_output:
                    detail = verbose_output[0]
                    state = detail.get("state", "")
                    is_up = state.lower() == "established"
                    uptime_str = detail.get("up_down_time", "")
                    uptime = parse_time(uptime_str) if uptime_str else -1

                    peer_detail = {
                        "up": is_up,
                        "local_as": int(parse_null(detail.get("local_as", local_as), local_as)),
                        "remote_as": int(parse_null(detail.get("remote_as", remote_as), remote_as)),
                        "router_id": router_id,
                        "local_address": detail.get("local_address", ""),
                        "routing_table": "default",
                        "local_address_configured": bool(detail.get("local_address", "")),
                        "local_port": int(parse_null(detail.get("local_port", 0), 0)),
                        "remote_address": detail.get("remote_address", peer_ip),
                        "remote_port": int(parse_null(detail.get("remote_port", 0), 0)),
                        "multihop": False,
                        "multipath": False,
                        "remove_private_as": False,
                        "import_policy": detail.get("import_route_policy", ""),
                        "export_policy": detail.get("export_route_policy", ""),
                        "input_messages": int(parse_null(detail.get("messages_received", 0), 0)),
                        "output_messages": int(parse_null(detail.get("messages_sent", 0), 0)),
                        "input_updates": int(parse_null(detail.get("update_messages_received", 0), 0)),
                        "output_updates": int(parse_null(detail.get("update_messages_sent", 0), 0)),
                        "messages_queued_out": 0,
                        "connection_state": state,
                        "previous_connection_state": "",
                        "last_event": "",
                        "suppress_4byte_as": False,
                        "local_as_prepend": False,
                        "holdtime": int(parse_null(detail.get("hold_time", 0), 0)),
                        "configured_holdtime": int(parse_null(detail.get("configured_hold_time", 0), 0)),
                        "keepalive": int(parse_null(detail.get("keepalive_interval", 0), 0)),
                        "configured_keepalive": int(parse_null(detail.get("configured_keepalive", 0), 0)),
                        "active_prefix_count": int(parse_null(peer_entry.get("active", 0), 0)),
                        "received_prefix_count": int(parse_null(peer_entry.get("pref_rcv", 0), 0)),
                        "accepted_prefix_count": int(parse_null(peer_entry.get("accepted", 0), 0)),
                        "suppressed_prefix_count": 0,
                        "advertised_prefix_count": int(parse_null(peer_entry.get("upstream", 0), 0)),
                        "flap_count": 0,
                    }
                else:
                    # Fallback: construct from summary data
                    state = peer_entry.get("state", "")
                    peer_detail = {
                        "up": state.lower() == "established",
                        "local_as": local_as,
                        "remote_as": remote_as,
                        "router_id": router_id,
                        "local_address": "",
                        "routing_table": "default",
                        "local_address_configured": False,
                        "local_port": 0,
                        "remote_address": peer_ip,
                        "remote_port": 0,
                        "multihop": False,
                        "multipath": False,
                        "remove_private_as": False,
                        "import_policy": "",
                        "export_policy": "",
                        "input_messages": 0,
                        "output_messages": 0,
                        "input_updates": 0,
                        "output_updates": 0,
                        "messages_queued_out": 0,
                        "connection_state": state,
                        "previous_connection_state": "",
                        "last_event": "",
                        "suppress_4byte_as": False,
                        "local_as_prepend": False,
                        "holdtime": 0,
                        "configured_holdtime": 0,
                        "keepalive": 0,
                        "configured_keepalive": 0,
                        "active_prefix_count": int(parse_null(peer_entry.get("active", 0), 0)),
                        "received_prefix_count": int(parse_null(peer_entry.get("pref_rcv", 0), 0)),
                        "accepted_prefix_count": int(parse_null(peer_entry.get("accepted", 0), 0)),
                        "suppressed_prefix_count": 0,
                        "advertised_prefix_count": int(parse_null(peer_entry.get("upstream", 0), 0)),
                        "flap_count": 0,
                    }

                vrf_key = "global"
                result.setdefault(vrf_key, {})
                result[vrf_key].setdefault(remote_as, [])
                result[vrf_key][remote_as].append(peer_detail)

        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_bgp_neighbors_detail: %s", e)

        return result

    def get_ipv6_neighbors_table(self):
        """Return IPv6 neighbors table."""
        neighbors = []
        try:
            command = self._get_command("ipv6.neighbors")
            structured_output = self._get_structured_output(command)
            for entry in structured_output:
                ipv6_addr = entry.get("ipv6_address", "")
                mac_address = entry.get("mac_address", "")
                interface = entry.get("interface", "")
                state = entry.get("state", "")
                age_str = entry.get("aging", "0")
                try:
                    age = float(age_str) if age_str not in ("-", "Aging", "") else 0.0
                except ValueError:
                    age = 0.0
                neighbors.append({
                    "interface": canonical_interface_name_comware(interface),
                    "mac": mac(mac_address) if mac_address and mac_address != "-" else "",
                    "ip": ipv6_addr,
                    "age": age,
                    "state": state,
                })
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_ipv6_neighbors_table: %s", e)
        return neighbors

    def get_ntp_peers(self):
        """Return NTP peers. Delegates to get_ntp_stats()."""
        ntp_peers = {}
        try:
            ntp_stats = self.get_ntp_stats()
            for entry in ntp_stats:
                remote = entry.get("remote", "")
                if remote:
                    ntp_peers[remote] = {}
        except Exception as e:
            logger.error("Error in get_ntp_peers: %s", e)
        return ntp_peers

    def get_ntp_servers(self):
        """Return NTP servers from device configuration."""
        ntp_servers = {}
        try:
            command = self._get_command("ntp.servers")
            structured_output = self._get_structured_output(
                command, "display_current-configuration_ntp-service"
            )
            for entry in structured_output:
                address = entry.get("address", "")
                if not address:
                    continue
                assoc_type = entry.get("association_type", "")
                ntp_servers[address] = {
                    "association_type": "server" if "server" in assoc_type else "peer",
                }
                version = entry.get("version", "")
                if version:
                    ntp_servers[address]["version"] = int(version)
                source = entry.get("source_interface", "")
                if source:
                    ntp_servers[address]["source_address"] = source
                vrf = entry.get("vpn_instance", "")
                if vrf:
                    ntp_servers[address]["network_instance"] = vrf
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_ntp_servers: %s", e)
        return ntp_servers

    def get_ntp_stats(self):
        """Return NTP statistics from device sessions."""
        ntp_stats = []
        try:
            command = self._get_command("ntp.stats")
            structured_output = self._get_structured_output(command)
            for entry in structured_output:
                clock_source = entry.get("clock_source", "")
                clock_status = entry.get("clock_status", "")
                is_synchronized = "master" in clock_status.lower() or "synchronized" in clock_status.lower()
                ntp_stats.append({
                    "remote": clock_source,
                    "referenceid": entry.get("reference_id", ""),
                    "synchronized": is_synchronized,
                    "stratum": int(parse_null(entry.get("clock_stratum", 0), 0)),
                    "type": "-",
                    "when": entry.get("last_update", ""),
                    "hostpoll": int(parse_null(entry.get("poll_interval", 0), 0)),
                    "reachability": int(parse_null(entry.get("reachability", 0), 0)),
                    "delay": float(parse_null(entry.get("delay", 0.0), 0.0)),
                    "offset": float(parse_null(entry.get("offset", 0.0), 0.0)),
                    "jitter": float(parse_null(entry.get("jitter", 0.0), 0.0)),
                })
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_ntp_stats: %s", e)
        return ntp_stats

    def get_snmp_information(self):
        """Return SNMP configuration information."""
        result = {
            "chassis_id": "",
            "community": {},
            "contact": "",
            "location": "",
        }
        try:
            # Get sys-info
            sys_cmd = self._get_command("snmp.sysinfo")
            sys_output = self._get_structured_output(
                sys_cmd, "display_snmp-agent_sys-info"
            )
            if sys_output:
                entry = sys_output[0]
                result["contact"] = entry.get("contact", "").strip()
                result["location"] = entry.get("location", "").strip()
                result["chassis_id"] = entry.get("chassis_id", "").strip()

            # Get community info from config
            comm_cmd = self._get_command("snmp.community")
            comm_output = self._get_structured_output(
                comm_cmd, "display_current-configuration_snmp-community"
            )
            for entry in comm_output:
                name = entry.get("community_name", "")
                mode = entry.get("mode", "")
                acl = entry.get("acl", "")
                if name:
                    result["community"][name] = {
                        "acl": acl,
                        "mode": mode,
                    }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_snmp_information: %s", e)
        return result

    def get_users(self):
        """Return configured users on the device."""
        users = {}
        try:
            command = self._get_command("users")
            structured_output = self._get_structured_output(command)
            for user_entry in structured_output:
                username = user_entry.get("username", "")
                if not username:
                    continue
                users[username] = {
                    "level": 0,
                    "password": "",
                    "sshkeys": [],
                }
            # Enrich with level and password from config
            # Use "configuration local-user" to get the full section including
            # authorization-attribute lines (| include only returns the header).
            config_command = self._get_command("users.config")
            config_output = self.send_command(config_command)
            current_user = ""
            for line in config_output.splitlines():
                user_match = re.match(r"^\s*local-user\s+(\S+)", line)
                if user_match:
                    current_user = user_match.group(1)
                    if current_user not in users:
                        users[current_user] = {"level": 0, "password": "", "sshkeys": []}
                    continue
                if current_user:
                    level_match = re.search(
                        r"authorization-attribute\s+(?:level|user-role)\s+(\S+)", line
                    )
                    if level_match:
                        level_str = level_match.group(1)
                        try:
                            new_level = int(level_str)
                        except ValueError:
                            role_map = {
                                "network-admin": 15,
                                "network-operator": 5,
                            }
                            for i in range(16):
                                role_map["level-{}".format(i)] = i
                            new_level = role_map.get(level_str, 0)
                        # Keep the highest privilege level when multiple
                        # authorization-attribute lines are present.
                        if new_level > users[current_user]["level"]:
                            users[current_user]["level"] = new_level
                    pwd_match = re.search(r"password\s+(?:simple|cipher|hash)\s+(\S+)", line)
                    if pwd_match:
                        users[current_user]["password"] = pwd_match.group(1)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_users: %s", e)
        return users

    def get_optics(self):
        """Return optical transceiver diagnostic information."""
        optics = {}
        try:
            command = self._get_command("optics")
            structured_output = self._get_structured_output(command)
            for entry in structured_output:
                interface = entry.get("interface", "")
                if not interface:
                    continue
                tx_power = float(parse_null(entry.get("tx_power", 0.0), 0.0))
                rx_power = float(parse_null(entry.get("rx_power", 0.0), 0.0))
                bias_current = float(parse_null(entry.get("bias_current", 0.0), 0.0))
                optics[interface] = {
                    "physical_channels": {
                        "channels": {
                            "index": 0,
                            "state": {
                                "input_power": {
                                    "instant": rx_power,
                                    "avg": 0.0,
                                    "min": 0.0,
                                    "max": 0.0,
                                },
                                "output_power": {
                                    "instant": tx_power,
                                    "avg": 0.0,
                                    "min": 0.0,
                                    "max": 0.0,
                                },
                                "laser_bias_current": {
                                    "instant": bias_current,
                                    "avg": 0.0,
                                    "min": 0.0,
                                    "max": 0.0,
                                },
                            },
                        }
                    }
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_optics: %s", e)
        return optics

    def get_probes_config(self):
        """Return NQA probe configuration."""
        probes = {}
        try:
            command = self._get_command("probes.config")
            structured_output = self._get_structured_output(
                command, "display_current-configuration_nqa"
            )
            # TextFSM produces one record per line; merge into grouped entries
            current_admin = ""
            current_test = ""
            for entry in structured_output:
                admin = entry.get("admin", "")
                test = entry.get("test", "")
                if admin:
                    current_admin = admin
                if test:
                    current_test = test
                if current_admin and current_test:
                    probes.setdefault(current_admin, {})
                    probes[current_admin].setdefault(current_test, {
                        "probe_type": "",
                        "target": "",
                        "source": "",
                        "probe_count": 0,
                        "test_interval": 0,
                    })
                    probe_type = entry.get("probe_type", "")
                    if probe_type:
                        probes[current_admin][current_test]["probe_type"] = probe_type
                    target = entry.get("target", "")
                    if target:
                        probes[current_admin][current_test]["target"] = target
                    source = entry.get("source", "")
                    if source:
                        probes[current_admin][current_test]["source"] = source
                    probe_count = entry.get("probe_count", "")
                    if probe_count:
                        probes[current_admin][current_test]["probe_count"] = int(probe_count)
                    test_interval = entry.get("test_interval", "")
                    if test_interval:
                        probes[current_admin][current_test]["test_interval"] = int(test_interval)
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_probes_config: %s", e)
        return probes

    def get_probes_results(self):
        """Return NQA probe test results."""
        results = {}
        try:
            command = self._get_command("probes.results")
            structured_output = self._get_structured_output(command)
            for entry in structured_output:
                admin = entry.get("admin", "")
                test = entry.get("test", "")
                if not admin or not test:
                    continue
                probe_count = int(parse_null(entry.get("probe_count", 0), 0))
                packet_loss_pct = float(parse_null(entry.get("packet_loss", 0.0), 0.0))
                last_test_loss = int(probe_count * packet_loss_pct / 100)
                rtt_str = entry.get("rtt", "0/0/0")
                rtt_parts = rtt_str.split("/")
                rtt_avg = float(parse_null(rtt_parts[2] if len(rtt_parts) > 2 else 0, 0.0))
                results.setdefault(admin, {})
                results[admin][test] = {
                    "target": "",
                    "source": "",
                    "probe_type": "",
                    "probe_count": probe_count,
                    "rtt": rtt_avg,
                    "round_trip_jitter": 0.0,
                    "last_test_loss": last_test_loss,
                    "current_test_min_delay": float(parse_null(entry.get("current_min_delay", 0.0), 0.0)),
                    "current_test_max_delay": float(parse_null(entry.get("current_max_delay", 0.0), 0.0)),
                    "current_test_avg_delay": float(parse_null(entry.get("current_avg_delay", 0.0), 0.0)),
                    "last_test_min_delay": float(parse_null(entry.get("last_min_delay", 0.0), 0.0)),
                    "last_test_max_delay": float(parse_null(entry.get("last_max_delay", 0.0), 0.0)),
                    "last_test_avg_delay": float(parse_null(entry.get("last_avg_delay", 0.0), 0.0)),
                    "global_test_min_delay": float(parse_null(entry.get("global_min_delay", 0.0), 0.0)),
                    "global_test_max_delay": float(parse_null(entry.get("global_max_delay", 0.0), 0.0)),
                    "global_test_avg_delay": float(parse_null(entry.get("global_avg_delay", 0.0), 0.0)),
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_probes_results: %s", e)
        return results

    def get_firewall_policies(self):
        self._raise_not_implemented("get_firewall_policies")

    def get_vlans(self):
        """
        Return structure being spit balled is as follows.
            * vlan_id (int)
                * name (text_type)
                * interfaces (list)

        By default, `vlan_name` == `vlan_description`. If both are default or not, \
        use `vlan_name`. If one of them is not the default value, use user-configured \
        value.

        Example::

            {
                1: {
                    "name": "default",
                    "interfaces": ["GigabitEthernet0/0/1", "GigabitEthernet0/0/2"]
                },
                2: {
                    "name": "vlan2",
                    "interfaces": []
                }
            }
        """
        vlans = {}

        try:
            command = self._get_command("vlans")
            structured_output = self._get_structured_output(command)
            for vlan_entry in structured_output:
                vlan_name = vlan_entry.get("name", "")
                vlan_desc = vlan_entry.get("description", "")
                vlan_id = vlan_entry.get("vlan_id")
                if vlan_id is None:
                    continue
                name = self._select_vlan_name(vlan_name, vlan_desc)
                vlans[int(vlan_id)] = {
                    "name": name,
                    "interfaces": vlan_entry.get("interfaces", [])
                }
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_vlans: %s", e)

        return vlans

    def get_irf_config(self):
        """
        Returns a dictionary of dictionaries where the first key is irf member ID,
        and the internal dictionary uses the irf port type as the key and port member as the value.

        Example::
            {
                1: {
                    'irf-port1': ['FortyGigE1/0/53', 'FortyGigE1/0/54'],
                    'irf-port2': [],
                }
                2: {
                    'irf-port1': [],
                    'irf-port2': ['FortyGigE2/0/53', 'FortyGigE2/0/54'],
                }
            }
        """
        irf_config = defaultdict(dict)

        try:
            command = self._get_command("irf.config")
            structured_output = self._get_structured_output(command)
            for config in structured_output:
                member_id = config.get("member_id", "")
                port_id = config.get("port_id", "")
                port_member = config.get("port_member", [])
                if member_id:
                    irf_config[int(member_id)]["irf-port%s" % port_id] = port_member
        except (KeyError, AttributeError, ComwareParserError) as e:
            logger.error("Error in get_irf_config: %s", e)

        return irf_config

    def is_irf(self):
        """
        Returns True if the IRF is setup.
        """
        config = self.get_irf_config()
        if config:
            return {"is_irf": True}
        else:
            return {"is_irf": False}

    def ping(
        self,
        destination: str,
        source: str = "",
        ttl: int = 255,
        timeout: int = 2,
        size: int = 100,
        count: int = 5,
        vrf: str = "",
        source_interface: str = "",
    ) -> models.PingResultDict:
        """Execute ping on the device and return a dictionary with the result.

        Args:
            destination: Host or IP address to ping.
            source: Source IP address to use (maps to ``-a`` on Comware).
            ttl: Time-to-live value (maps to ``-h`` on Comware).
            timeout: Timeout in seconds (converted to milliseconds for Comware ``-t``).
            size: Packet size in bytes (maps to ``-s`` on Comware).
            count: Number of ping packets to send (maps to ``-c`` on Comware).
            vrf: VRF / VPN instance name (maps to ``-vpn-instance`` on Comware).
            source_interface: Source interface whose IP is used (maps to ``-i``).

        Returns:
            A dictionary with ``success`` (probes_sent, packet_loss, rtt_min/max/avg/stddev,
            results) or ``error`` key.
        """
        ping_dict: models.PingResultDict = {}

        try:
            # Build the H3C Comware ping command
            # Comware timeout (-t) is in milliseconds; NAPALM uses seconds
            timeout_ms = timeout * 1000

            command_parts = ["ping"]
            if vrf:
                command_parts.append("-vpn-instance {}".format(vrf))
            if source:
                command_parts.append("-a {}".format(source))
            elif source_interface:
                command_parts.append("-i {}".format(source_interface))
            command_parts.append("-c {}".format(count))
            command_parts.append("-h {}".format(ttl))
            command_parts.append("-s {}".format(size))
            command_parts.append("-t {}".format(timeout_ms))
            command_parts.append(destination)

            command = " ".join(command_parts)
            output = self.send_command(command)

            # Check for error indicators in output
            if "Error:" in output or "Unknown host" in output or "Invalid" in output:
                ping_dict["error"] = output.strip()
                return ping_dict

            # Initialize success structure
            ping_dict["success"] = {
                "probes_sent": 0,
                "packet_loss": 0,
                "rtt_min": 0.0,
                "rtt_max": 0.0,
                "rtt_avg": 0.0,
                "rtt_stddev": 0.0,
                "results": [],
            }

            # Parse per-probe results
            probe_re = re.compile(
                r"(\d+) bytes from (\S+): icmp_seq=(\d+) ttl=(\d+) time=([\d.]+) ms"
            )
            results_list = []
            for line in output.splitlines():
                match = probe_re.search(line)
                if match:
                    probe_ip = ip(match.group(2))
                    probe_rtt = float(match.group(5))
                    results_list.append({
                        "ip_address": probe_ip,
                        "rtt": probe_rtt,
                    })

            ping_dict["success"]["results"] = results_list

            # Parse statistics summary
            stats_re = re.compile(
                r"(\d+) packet\(s\) transmitted, (\d+) packet\(s\) received, ([\d.]+)% packet loss"
            )
            stats_match = stats_re.search(output)
            if stats_match:
                probes_sent = int(stats_match.group(1))
                probes_received = int(stats_match.group(2))
                ping_dict["success"]["probes_sent"] = probes_sent
                ping_dict["success"]["packet_loss"] = probes_sent - probes_received

            # Parse RTT summary
            rtt_re = re.compile(
                r"round-trip min/avg/max/std-dev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms"
            )
            rtt_match = rtt_re.search(output)
            if rtt_match:
                ping_dict["success"]["rtt_min"] = float(rtt_match.group(1))
                ping_dict["success"]["rtt_avg"] = float(rtt_match.group(2))
                ping_dict["success"]["rtt_max"] = float(rtt_match.group(3))
                ping_dict["success"]["rtt_stddev"] = float(rtt_match.group(4))

        except Exception as e:
            logger.error("Error in ping: %s", e)
            ping_dict["error"] = str(e)

        return ping_dict

    def traceroute(
        self,
        destination: str,
        source: str = "",
        ttl: int = 255,
        timeout: int = 2,
        vrf: str = "",
    ) -> models.TracerouteResultDict:
        """Execute traceroute on the device and return a dictionary with the result.

        Args:
            destination: Host or IP address to trace.
            source: Source IP address to use (maps to ``-a`` on Comware).
            ttl: Maximum number of hops (maps to ``-m`` on Comware).
            timeout: Timeout in seconds for each probe (maps to ``-w`` on Comware).
            vrf: VRF / VPN instance name (maps to ``-vpn-instance`` on Comware).

        Returns:
            A dictionary with ``success`` (keyed by hop ID, each containing
            ``probes`` dict with rtt/ip_address/host_name) or ``error`` key.
        """
        traceroute_dict: models.TracerouteResultDict = {}

        try:
            # Build the H3C Comware tracert command
            command_parts = ["tracert"]
            if vrf:
                command_parts.append("-vpn-instance {}".format(vrf))
            if source:
                command_parts.append("-a {}".format(source))
            command_parts.append("-m {}".format(ttl))
            command_parts.append("-w {}".format(timeout))
            command_parts.append(destination)

            command = " ".join(command_parts)
            # Traceroute can take a while; use a generous read_timeout
            read_timeout = max(ttl * timeout, 100)
            output = self.send_command(command, read_timeout=read_timeout)

            # Check for error indicators
            if "Error:" in output or "Unknown host" in output or "Invalid" in output:
                traceroute_dict["error"] = output.strip()
                return traceroute_dict

            # Parse hop lines
            # Each hop line format:
            #   <hop_id>  <hostname> (<ip>)  <rtt1> ms  <rtt2> ms  <rtt3> ms
            #   <hop_id>  * * *
            hop_line_re = re.compile(r"^\s*(\d+)\s+(.*)$")
            host_ip_re = re.compile(r"^(\S+)\s+\((\S+)\)")
            probe_re = re.compile(r"([\d.]+)\s+ms|\*")

            results: dict = {}

            for line in output.splitlines():
                hop_match = hop_line_re.match(line)
                if not hop_match:
                    continue

                hop_id = int(hop_match.group(1))
                hop_data = hop_match.group(2)

                results[hop_id] = {"probes": {}}

                # Try to extract hostname and IP from the beginning
                host_ip_match = host_ip_re.match(hop_data)
                if host_ip_match:
                    host_name = host_ip_match.group(1)
                    ip_address = ip(host_ip_match.group(2))
                    probes_part = hop_data[host_ip_match.end():].strip()
                else:
                    # No hostname in parentheses; first token might be an IP
                    host_name = ""
                    first_token = hop_data.split()[0] if hop_data.split() else ""
                    try:
                        ip_address = ip(first_token)
                    except Exception:
                        ip_address = first_token
                    probes_part = hop_data[len(first_token):].strip()

                # Parse probes
                probe_matches = probe_re.findall(probes_part)
                for probe_idx, probe_val in enumerate(probe_matches, start=1):
                    if probe_val:  # Non-empty means a valid RTT value
                        results[hop_id]["probes"][probe_idx] = {
                            "rtt": float(probe_val),
                            "ip_address": ip_address,
                            "host_name": host_name,
                        }
                    else:
                        # Asterisk (timeout)
                        results[hop_id]["probes"][probe_idx] = {
                            "rtt": 0.0,
                            "ip_address": ip_address,
                            "host_name": host_name,
                        }

            traceroute_dict["success"] = results

        except Exception as e:
            logger.error("Error in traceroute: %s", e)
            traceroute_dict["error"] = str(e)

        return traceroute_dict

    # ------------------------------------------------------------------
    # Configuration management helpers
    # ------------------------------------------------------------------

    def _read_candidate_config(self, filename=None, config=None):
        """Read candidate config from file or string. File takes precedence."""
        if filename is not None:
            with open(filename, "r") as f:
                return f.read()
        elif config is not None:
            return config
        else:
            raise ValueError("Either filename or config must be provided")

    def _check_config_errors(self, output: str) -> list:
        """Check Comware command output for error patterns. Returns list of error lines."""
        errors = []
        for line in output.splitlines():
            for pattern in COMWARE_CONFIG_ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    break
        return errors

    def _get_running_config(self) -> str:
        """Retrieve the current running configuration."""
        command = self._get_command("config.running")
        return self.send_command(command)

    def _gen_full_path(self, filename: str) -> str:
        """Generate full file path on remote device."""
        return f"{self._dest_file_system}/{filename}"

    def _check_archive_feature(self) -> bool:
        """Check if archive configuration is enabled on the device."""
        try:
            output = self.send_command("display archive configuration")
            return "Archive configuration" in output and "not enabled" not in output.lower()
        except Exception:
            return False

    def _transfer_file_to_device(self, source_config: str, dest_file: str) -> None:
        """Transfer a config string to the device filesystem via SCP.

        Writes the config to a temporary local file, then uses
        HPComwareFileTransfer to SCP it to the device.
        """
        tmp_file = None
        try:
            # Write config to temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(source_config)
                tmp_file = f.name

            with HPComwareFileTransfer(
                ssh_conn=self.device,
                source_file=tmp_file,
                dest_file=dest_file,
                file_system=self._dest_file_system,
                direction="put",
            ) as transfer:
                if not transfer.verify_space_available():
                    raise ReplaceConfigException(
                        "Insufficient space available on remote device"
                    )
                transfer.transfer_file()
                if not transfer.verify_file():
                    raise ReplaceConfigException(
                        f"File transfer verification failed for {dest_file}"
                    )
        finally:
            if tmp_file and os.path.isfile(tmp_file):
                os.remove(tmp_file)

    def _save_running_to_file(self, dest_file: str) -> None:
        """Save running configuration to a file on the device."""
        full_path = self._gen_full_path(dest_file)
        # Use Comware's built-in save to file command
        self.device.send_command(
            f"save {full_path}",
            read_timeout=60,
        )

    # ------------------------------------------------------------------
    # Configuration management methods
    # ------------------------------------------------------------------

    def load_replace_candidate(self, filename=None, config=None):
        """Load candidate config for replace operation. Stored locally only."""
        try:
            self._candidate_config = self._read_candidate_config(filename, config)
        except (IOError, OSError) as e:
            raise ReplaceConfigException(f"Failed to read candidate config: {e}")
        except ValueError as e:
            raise ReplaceConfigException(str(e))

        self._config_replace = True
        self._loaded = True
        logger.info("Loaded replace candidate config (%d bytes)", len(self._candidate_config))

    def load_merge_candidate(self, filename=None, config=None):
        """Load candidate config for merge operation. Stored locally only."""
        try:
            self._candidate_config = self._read_candidate_config(filename, config)
        except (IOError, OSError) as e:
            raise MergeConfigException(f"Failed to read candidate config: {e}")
        except ValueError as e:
            raise MergeConfigException(str(e))

        self._config_replace = False
        self._loaded = True
        logger.info("Loaded merge candidate config (%d bytes)", len(self._candidate_config))

    def compare_config(self):
        """Compare candidate config with running config. Returns diff string."""
        if not self._loaded:
            return ""

        running_config = self._get_running_config()
        candidate_config = self._candidate_config

        if self._config_replace:
            # Full unified diff for replace mode
            diff = difflib.unified_diff(
                running_config.splitlines(),
                candidate_config.splitlines(),
                fromfile="running",
                tofile="candidate",
                lineterm="",
            )
            diff_lines = list(diff)
            # Strip the header lines (--- running, +++ candidate)
            result_lines = [line for line in diff_lines
                           if line.startswith("+") or line.startswith("-")]
            return "\n".join(result_lines)
        else:
            # For merge mode: show candidate lines not already in running
            running_lines = {line.strip() for line in running_config.splitlines()}
            diff_lines = []
            for line in candidate_config.splitlines():
                stripped = line.strip()
                if stripped and stripped not in running_lines:
                    diff_lines.append("+" + line)
            return "\n".join(diff_lines)

    def commit_config(self, message="", revert_in=None):
        """Commit the candidate configuration."""
        if not self._loaded:
            raise ConfigManagementError("No candidate configuration loaded")

        if message:
            logger.warning("Commit message not supported on Comware; ignoring: %s", message)

        if revert_in is not None:
            raise NotImplementedError(
                "commit_config with revert_in is not yet supported on this platform"
            )

        # Save pre-commit running config for rollback
        self._pre_commit_config = self._get_running_config()

        if self._config_replace:
            self._commit_replace()
        else:
            self._commit_merge()

        # Clear candidate state
        self._loaded = False
        self._candidate_config = ""
        logger.info("Config committed successfully")

    def _commit_merge(self):
        """Apply candidate config by merging (system-view + commands)."""
        commands = [line for line in self._candidate_config.splitlines() if line.strip()]
        if not commands:
            logger.info("No commands to apply; empty candidate config")
            return

        try:
            output = self.device.send_config_set(
                commands,
                enter_config_mode=True,
                exit_config_mode=True,
            )
        except Exception as e:
            raise MergeConfigException(f"Failed to apply config: {e}")

        # Check for errors in output
        errors = self._check_config_errors(output)
        if errors:
            logger.error("Config errors detected: %s", errors)
            try:
                self.rollback()
            except Exception as rollback_err:
                logger.error("Automatic rollback failed: %s", rollback_err)
            raise MergeConfigException(
                f"Configuration merge failed; automatic rollback attempted. "
                f"Errors: {'; '.join(errors)}"
            )

        # Save running config to startup
        try:
            self.device.save_config()
            logger.info("Config saved to startup")
        except Exception as e:
            raise ConfigManagementError(f"Config applied but save failed: {e}")

    def _commit_replace(self):
        """Apply candidate config by replacing the entire running configuration.

        Requires ``archive configuration`` to be enabled on the device.
        Uses ``configuration replace file`` to atomically replace the
        running config.
        """
        if not self._check_archive_feature():
            raise ReplaceConfigException(
                "Configuration replace requires 'archive configuration' to be enabled. "
                "Enable it with: archive configuration location <dir> max <n>"
            )

        # Transfer candidate config to device
        try:
            self._transfer_file_to_device(
                source_config=self._candidate_config,
                dest_file=self._candidate_cfg,
            )
        except Exception as e:
            raise ReplaceConfigException(f"Failed to transfer candidate config: {e}")

        # Execute configuration replace
        full_path = self._gen_full_path(self._candidate_cfg)
        try:
            output = self.device.send_command(
                f"configuration replace file {full_path}",
                read_timeout=120,
            )
        except Exception as e:
            raise ReplaceConfigException(f"Configuration replace failed: {e}")

        if "Error" in output or "Failed" in output:
            raise ReplaceConfigException(
                f"Configuration replace failed: {output}"
            )

        # Save running config to startup
        try:
            self.device.save_config()
            logger.info("Config saved to startup after replace")
        except Exception as e:
            raise ConfigManagementError(f"Config replaced but save failed: {e}")

    def discard_config(self):
        """Discard the loaded candidate configuration."""
        self._candidate_config = ""
        self._config_replace = False
        self._loaded = False
        logger.info("Discarded candidate configuration")

    def rollback(self):
        """Rollback to the pre-commit configuration.

        Uses ``configuration replace file`` when archive is enabled
        (true rollback with deletion support). Falls back to re-applying
        the pre-commit snapshot via merge (idempotent replay, will NOT
        remove commands added after the snapshot).
        """
        if not self._pre_commit_config:
            raise ConfigManagementError(
                "No pre-commit configuration snapshot available for rollback"
            )

        # Clear any current candidate to avoid interference
        self._candidate_config = ""
        self._loaded = False

        try:
            if self._check_archive_feature():
                self._rollback_archive()
            else:
                self._rollback_snapshot()
        except ConfigManagementError:
            raise
        except Exception as e:
            raise ConfigManagementError(f"Rollback failed: {e}")

        # Clear the pre-commit snapshot
        self._pre_commit_config = ""
        logger.info("Rollback completed successfully")

    def _rollback_archive(self):
        """Rollback using configuration replace file (archive-based).

        Requires ``archive configuration`` to be enabled. Transfers the
        pre-commit snapshot to the device and uses ``configuration replace
        file`` for a true atomic rollback.
        """
        try:
            self._transfer_file_to_device(
                source_config=self._pre_commit_config,
                dest_file=self._rollback_cfg,
            )
        except Exception as e:
            logger.warning("Archive rollback: file transfer failed, falling back to snapshot: %s", e)
            self._rollback_snapshot()
            return

        full_path = self._gen_full_path(self._rollback_cfg)
        output = self.device.send_command(
            f"configuration replace file {full_path}",
            read_timeout=120,
        )

        if "Error" in output or "Failed" in output:
            logger.warning("Archive rollback: replace failed, falling back to snapshot")
            self._rollback_snapshot()
            return

        self.device.save_config()

    def _rollback_snapshot(self):
        """Rollback by re-applying the pre-commit running config snapshot.

        This is an idempotent replay — it will re-apply existing commands
        but will NOT remove commands added after the snapshot.
        """
        commands = [line for line in self._pre_commit_config.splitlines() if line.strip()]
        self.device.send_config_set(
            commands,
            enter_config_mode=True,
            exit_config_mode=True,
        )
        self.device.save_config()

    def confirm_commit(self):
        """Confirm a pending commit-confirm operation. Not yet supported."""
        raise NotImplementedError("confirm_commit is not yet supported on this platform")

    def has_pending_commit(self):
        """Check if there is a pending commit-confirm operation."""
        return False
