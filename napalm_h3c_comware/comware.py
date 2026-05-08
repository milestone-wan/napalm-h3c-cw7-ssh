# Copyright 2022 Eric Wu. All rights reserved.
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

"""
Napalm driver for H3C Comware V7/V9 devices.

Read https://napalm.readthedocs.io for more information.
"""

import logging
import re
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

from napalm.base.base import NetworkDriver
from napalm.base.helpers import (
    textfsm_extractor,
    mac,
)
from napalm.base.netmiko_helpers import netmiko_args
from netmiko.hp.hp_comware import HPComwareBase

from .commands import default_command_registry
from .exceptions import ParserError, UnsupportedCommandError
from .profiles import build_device_profile
from .utils.helpers import (
    canonical_interface_name_comware,
    parse_time,
    parse_null,
    strptime,
    get_value_from_list_of_dict,
)

logger = logging.getLogger(__name__)


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
        self.netmiko_optional_args = netmiko_args(optional_args)
        if "timeout" not in self.netmiko_optional_args:
            self.netmiko_optional_args["timeout"] = self.timeout
        self.profile = None
        self.command_registry = default_command_registry()
        self._command_cache: Dict[Tuple[str, str], list] = {}

    def open(self):
        """Open a connection to the device."""
        device_type = "hp_comware"
        self.device: HPComwareBase = self._netmiko_open(
            device_type, netmiko_optional_args=self.netmiko_optional_args
        )
        logger.info("Connected to %s", self.hostname)
        self._command_cache = {}

        if self.force_english:
            self._force_english_output()

        self._discover_profile()

    def close(self):
        logger.info("Disconnecting from %s", self.hostname)
        self._netmiko_close()

    def send_command(self, command: str, *args, **kwargs):
        logger.debug("Sending command: %s", command)
        try:
            return self.device.send_command(command, *args, **kwargs)
        except Exception as e:
            logger.warning("Command failed, attempting reconnect: %s", e)
            try:
                self._reconnect()
                return self.device.send_command(command, *args, **kwargs)
            except Exception as e2:
                logger.error("Reconnect and retry failed: %s", e2)
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
        if self.force_english:
            self._force_english_output()
        logger.info("Reconnected to %s", self.hostname)

    def is_alive(self):
        if self.device is None:
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
        """Build device profile from display version output."""
        try:
            structured = self._get_structured_output("display version")
            if isinstance(structured, list) and len(structured) == 1:
                info = structured[0]
                model = info.get("model", "")
                os_version = info.get("os_version", "")
                self.profile = build_device_profile(
                    model=model,
                    os_version=os_version,
                    version_output="",
                )
                logger.info("Device profile: %s", self.profile)
            else:
                logger.warning("Could not determine device profile from display version")
        except Exception as e:
            logger.warning("Profile discovery failed: %s", e)

    def _get_command(self, key: str) -> str:
        """Resolve a command string from the registry for the current profile."""
        if self.profile is not None:
            spec = self.command_registry.resolve(key, self.profile)
            return spec.command
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
            raise ParserError(
                f"Failed to parse output of '{command}' with template '{template_name}': {e}"
            ) from e
        if not result:
            logger.warning("Empty TextFSM result for command=%s template=%s", command, template_name)
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

            # hostname
            prompt = self.device.find_prompt()
            hostname = prompt[1:-1] if len(prompt) > 2 else prompt

            # interfaces
            structured_int_info = self._get_structured_output(self._get_command("facts.interfaces"))
            for interface in structured_int_info:
                interface_list.append(interface.get("interface"))

            # serial number
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

        except (KeyError, AttributeError, ParserError) as e:
            logger.error("Error in get_facts: %s", e)

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
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
            logger.error("Error in get_lldp_neighbors: %s", e)

        return lldp

    def get_bgp_neighbors(self):
        self._raise_not_implemented("get_bgp_neighbors")

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
        except (KeyError, AttributeError, ParserError) as e:
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
                    power_key = "slot %s power %s" % (slot, power_id)
                elif chassis != "":
                    power_key = "chassis %s power %s" % (chassis, power_id)
                else:
                    power_key = "power %s" % (power_id)

                power[power_key] = {
                    "status": status,
                    "capacity": -1,
                    "output": output
                }
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
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
                is_alert = True if float(temp) >= float(alert) else False
                is_critical = True if float(temp) >= float(critical) else False

                if chassis != "":
                    temp_key = "chassis %s slot %s sensor %s" % (
                        chassis, slot, sensor)
                else:
                    temp_key = "slot %s sensor %s" % (slot, sensor)
                temperature[temp_key] = {
                    "temperature": float(temp),
                    "is_alert": is_alert,
                    "is_critical": is_critical,
                }
        except (KeyError, AttributeError, ParserError) as e:
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
        self._raise_not_implemented("get_interfaces_counters")

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
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
            logger.error("Error in get_arp_table: %s", e)

        return arp_table

    def get_interfaces_ip(self):
        interfaces = {}

        try:
            command = self._get_command("interfaces.ipv4")
            structured_output = self._get_structured_output(command)
            for iface_entry in structured_output:
                interface = iface_entry.get("interface", "")
                ip_list = iface_entry.get("ip_address", [])
                ipv4 = {}
                if ip_list and len(ip_list) > 0:
                    for ip in ip_list:
                        parts = ip.split("/")
                        if len(parts) == 2:
                            ipv4[parts[0]] = {"prefix_length": int(parts[1])}
                    interfaces[interface] = {
                        "ipv4": ipv4
                    }
        except (KeyError, AttributeError, ParserError) as e:
            logger.error("Error in get_interfaces_ip: %s", e)

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
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
            logger.error("Error in get_mac_address_table: %s", e)

        return mac_address_table

    def get_route_to(self, destination="", protocol="", longer=False):
        self._raise_not_implemented("get_route_to")

    def get_config(self, retrieve="all", full=False, sanitized=False):
        configs = {"startup": "", "running": "", "candidate": ""}
        # Not Supported
        if full:
            pass
        if retrieve.lower() in ("running", "all"):
            command = self._get_command("config.running")
            configs["running"] = self.send_command(command)
        if retrieve.lower() in ("startup", "all"):
            command = self._get_command("config.startup")
            configs["startup"] = self.send_command(command)
        # Ignore, plaintext will be encrypted.
        # Remove secret data ? Not Implemented.
        if sanitized:
            pass
        return configs

    def get_network_instances(self, name: str = ""):
        self._raise_not_implemented("get_network_instances")

    def get_bgp_config(self, group="", neighbor=""):
        self._raise_not_implemented("get_bgp_config")

    def get_bgp_neighbors_detail(self, neighbor_address=""):
        self._raise_not_implemented("get_bgp_neighbors_detail")

    def get_ipv6_neighbors_table(self):
        self._raise_not_implemented("get_ipv6_neighbors_table")

    def get_ntp_peers(self):
        self._raise_not_implemented("get_ntp_peers")

    def get_ntp_servers(self):
        self._raise_not_implemented("get_ntp_servers")

    def get_ntp_stats(self):
        self._raise_not_implemented("get_ntp_stats")

    def get_snmp_information(self):
        self._raise_not_implemented("get_snmp_information")

    def get_users(self):
        self._raise_not_implemented("get_users")

    def get_optics(self):
        self._raise_not_implemented("get_optics")

    def get_probes_config(self):
        self._raise_not_implemented("get_probes_config")

    def get_probes_results(self):
        self._raise_not_implemented("get_probes_results")

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
        except (KeyError, AttributeError, ParserError) as e:
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
        except (KeyError, AttributeError, ParserError) as e:
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

    def ping(self, destination, source="", ttl=255, timeout=2, size=100, count=5, vrf=""):
        self._raise_not_implemented("ping")

    def traceroute(self, destination, source="", ttl=255, timeout=2, vrf=""):
        self._raise_not_implemented("traceroute")

    def load_replace_candidate(self, filename=None, config=None):
        self._raise_not_implemented("load_replace_candidate")

    def load_merge_candidate(self, filename=None, config=None):
        self._raise_not_implemented("load_merge_candidate")

    def compare_config(self):
        self._raise_not_implemented("compare_config")

    def commit_config(self, message="", revert_in=None):
        self._raise_not_implemented("commit_config")

    def discard_config(self):
        self._raise_not_implemented("discard_config")

    def rollback(self):
        self._raise_not_implemented("rollback")

    def confirm_commit(self):
        self._raise_not_implemented("confirm_commit")

    def has_pending_commit(self):
        self._raise_not_implemented("has_pending_commit")
