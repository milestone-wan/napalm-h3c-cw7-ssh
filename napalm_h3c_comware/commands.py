"""Command registry primitives for profile-aware Comware getters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

from .exceptions import UnsupportedCommandError
from .profiles import ComwareMajorVersion, DeviceProfile, DeviceRole


@dataclass(frozen=True)
class CommandSpec:
    """A command, parser template, and profile support declaration."""

    key: str
    command: str
    template_name: Optional[str] = None
    getter: Optional[str] = None
    versions: FrozenSet[ComwareMajorVersion] = field(default_factory=frozenset)
    roles: FrozenSet[DeviceRole] = field(default_factory=frozenset)
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    notes: str = ""

    def supports(self, profile: DeviceProfile) -> bool:
        if self.versions and profile.major_version not in self.versions:
            return False
        if self.roles and profile.role not in self.roles:
            return False
        if self.capabilities and not self.capabilities.issubset(profile.capabilities):
            return False
        return True

    @property
    def effective_template_name(self) -> str:
        if self.template_name:
            return self.template_name
        return "_".join(self.command.split())


class CommandRegistry:
    """Registry used to resolve commands for a specific device profile."""

    def __init__(self, specs: Iterable[CommandSpec] = ()):
        self._specs: Dict[str, Tuple[CommandSpec, ...]] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: CommandSpec) -> None:
        self._specs[spec.key] = (*self._specs.get(spec.key, ()), spec)

    def get(self, key: str) -> Tuple[CommandSpec, ...]:
        return self._specs.get(key, ())

    def resolve(self, key: str, profile: DeviceProfile) -> CommandSpec:
        for spec in self.get(key):
            if spec.supports(profile):
                return spec
        raise UnsupportedCommandError(f"No command spec for key={key!r} and profile={profile!r}")


COMMON_VERSIONS = frozenset({ComwareMajorVersion.V7, ComwareMajorVersion.V9})
SWITCH_AND_ROUTER = frozenset({DeviceRole.SWITCH, DeviceRole.ROUTER})
SWITCH_ONLY = frozenset({DeviceRole.SWITCH})


DEFAULT_COMMAND_SPECS = (
    CommandSpec(
        key="facts.version",
        getter="get_facts",
        command="display version",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="facts.interfaces",
        getter="get_facts",
        command="display interface",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="facts.serial",
        getter="get_facts",
        command="display device manuinfo",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="interfaces",
        getter="get_interfaces",
        command="display interface",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="interfaces.ipv4",
        getter="get_interfaces_ip",
        command="display ip interface",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="interfaces.ipv6",
        getter="get_interfaces_ip",
        command="display ipv6 interface",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="lldp.neighbors",
        getter="get_lldp_neighbors",
        command="display lldp neighbor-information verbose",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="lldp.neighbors.detail",
        getter="get_lldp_neighbors_detail",
        command="display lldp neighbor-information verbose",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="arp",
        getter="get_arp_table",
        command="display arp",
        template_name="display_arp",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="environment.cpu",
        getter="get_environment",
        command="display cpu-usage summary",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="environment.memory",
        getter="get_environment",
        command="display memory",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="environment.power",
        getter="get_environment",
        command="display power",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="environment.fan",
        getter="get_environment",
        command="display fan",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="environment.temperature",
        getter="get_environment",
        command="display environment",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="mac.table",
        getter="get_mac_address_table",
        command="display mac-address",
        versions=COMMON_VERSIONS,
        roles=SWITCH_ONLY,
        notes="Switch-oriented command; router support is unknown.",
    ),
    CommandSpec(
        key="mac.move",
        getter="get_mac_address_move_table",
        command="display mac-address mac-move",
        versions=COMMON_VERSIONS,
        roles=SWITCH_ONLY,
        notes="H3C extension for switch operations.",
    ),
    CommandSpec(
        key="vlans",
        getter="get_vlans",
        command="display vlan all",
        versions=COMMON_VERSIONS,
        roles=SWITCH_ONLY,
        notes="Switch-oriented command; router support is unknown.",
    ),
    CommandSpec(
        key="config.running",
        getter="get_config",
        command="display current-configuration",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="config.startup",
        getter="get_config",
        command="display saved-configuration",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="irf.config",
        getter="get_irf_config",
        command="display current-configuration configuration irf-port",
        versions=COMMON_VERSIONS,
        roles=SWITCH_ONLY,
        notes="H3C extension, not a standard NAPALM getter.",
    ),
    # --- get_route_to ---
    CommandSpec(
        key="route.table",
        getter="get_route_to",
        command="display ip routing-table",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="route.table.verbose",
        getter="get_route_to",
        command="display ip routing-table {} verbose",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
        notes="{} replaced by destination prefix.",
    ),
    # --- get_network_instances ---
    CommandSpec(
        key="vpn.instance",
        getter="get_network_instances",
        command="display ip vpn-instance",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="vpn.instance.detail",
        getter="get_network_instances",
        command="display ip vpn-instance instance-name {}",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
        notes="{} replaced by instance name.",
    ),
    # --- get_bgp_neighbors ---
    CommandSpec(
        key="bgp.summary",
        getter="get_bgp_neighbors",
        command="display bgp",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
        notes="Extract BGP router_id and local AS.",
    ),
    CommandSpec(
        key="bgp.peer",
        getter="get_bgp_neighbors",
        command="display bgp peer ipv4",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_bgp_neighbors_detail ---
    CommandSpec(
        key="bgp.peer.verbose",
        getter="get_bgp_neighbors_detail",
        command="display bgp peer {} verbose",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
        notes="{} replaced by peer IP; expensive per-peer iteration.",
    ),
    # --- get_users ---
    CommandSpec(
        key="users",
        getter="get_users",
        command="display local-user",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="users.config",
        getter="get_users",
        command="display current-configuration configuration local-user",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
        notes="Config enrichment for level/password via full local-user config section.",
    ),
    # --- get_ipv6_neighbors_table ---
    CommandSpec(
        key="ipv6.neighbors",
        getter="get_ipv6_neighbors_table",
        command="display ipv6 neighbors",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_ntp_servers ---
    CommandSpec(
        key="ntp.servers",
        getter="get_ntp_servers",
        command="display current-configuration | include ntp-service",
        template_name="display_current-configuration_ntp-service",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_snmp_information ---
    CommandSpec(
        key="snmp.sysinfo",
        getter="get_snmp_information",
        command="display snmp-agent sys-info",
        template_name="display_snmp-agent_sys-info",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    CommandSpec(
        key="snmp.community",
        getter="get_snmp_information",
        command="display current-configuration | include snmp-agent community",
        template_name="display_current-configuration_snmp-community",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_probes_config ---
    CommandSpec(
        key="probes.config",
        getter="get_probes_config",
        command="display current-configuration | include nqa",
        template_name="display_current-configuration_nqa",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_interfaces_counters ---
    CommandSpec(
        key="interfaces.counters",
        getter="get_interfaces_counters",
        command="display interface",
        template_name="display_interface_counters",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_ntp_stats ---
    CommandSpec(
        key="ntp.stats",
        getter="get_ntp_stats",
        command="display ntp-service sessions",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_optics ---
    CommandSpec(
        key="optics",
        getter="get_optics",
        command="display transceiver diagnosis interface",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_bgp_config ---
    CommandSpec(
        key="bgp.config",
        getter="get_bgp_config",
        command="display current-configuration configuration bgp",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
    # --- get_probes_results ---
    CommandSpec(
        key="probes.results",
        getter="get_probes_results",
        command="display nqa result",
        versions=COMMON_VERSIONS,
        roles=SWITCH_AND_ROUTER,
    ),
)


def default_command_registry() -> CommandRegistry:
    """Return a registry preloaded with current command mappings."""
    return CommandRegistry(DEFAULT_COMMAND_SPECS)
