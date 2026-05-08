# Getters Support Matrix

This document tracks the intended NAPALM API coverage for the H3C Comware driver. The long-term target is to evaluate every method currently represented in the NAPALM getters support matrix, while documenting H3C Comware V7/V9 switch and router limitations clearly.

## Scope

- Brand: H3C.
- Network OS: Comware V7 and Comware V9.
- Device roles: switches and routers.
- Excluded devices: firewalls and non-Comware platforms.
- Transport baseline: SSH through Netmiko.

## Status Values

| Status | Meaning |
| --- | --- |
| `supported` | Implemented, returns a NAPALM-compatible schema, and has at least basic validation. |
| `partial` | Implemented or partly implemented, but has known field, platform, parser, IPv4/IPv6, role, or validation limitations. |
| `planned` | In the roadmap, but not currently production-ready. |
| `unsupported` | Not supported for the target H3C Comware switch/router scope, or not planned. |
| `deprecated` | Present for compatibility but should not be extended without redesign. |
| `unknown` | Current code and fixtures are insufficient to determine support status. |

## Matrix Maintenance Rules

- Mark a method as `supported` only when the method maps to the NAPALM schema and has validation coverage.
- Use `partial` for existing code that is useful but not yet verified across V7/V9 or switch/router profiles.
- Use `planned` for methods required by the NAPALM matrix but not implemented yet.
- Use `unsupported` only when there is a clear scope or platform reason.
- Planned or unsupported methods should have explicit driver entries that raise `NotImplementedError` instead of silently returning `None`.
- Do not document unverified models, Comware patch versions, or fields as supported.
- When production command output is added, record the model, version, role, command, parser, and expected normalized result.

## Core Driver Methods

| Method | Status | Current source | Notes |
| --- | --- | --- | --- |
| `open` | `partial` | Netmiko `hp_comware` | Current transport is SSH/Netmiko; V7/V9 discovery is not profile-aware yet. |
| `close` | `partial` | Netmiko close | Basic session close only. |
| `is_alive` | `partial` | Netmiko `is_alive()` | Existing implementation. |
| `cli` | `partial` | Raw Netmiko commands | Useful helper; command authorization and sanitization are caller responsibility. |
| `ping` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `traceroute` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `load_template` | `planned` | TBD | Inherited from NAPALM base until template strategy is designed. |

## Standard Getters

| Getter | Status | Current command/template | Notes |
| --- | --- | --- | --- |
| `get_facts` | `partial` | `display version`, `display interface`, `display device manuinfo` | Existing V7-oriented implementation; V9/router validation needed. |
| `get_interfaces` | `partial` | `display interface` | Existing implementation; parser is known to be broad and needs redesign for counters/output variants. |
| `get_interfaces_ip` | `partial` | `display ip interface`, `display ipv6 interface` | IPv4 + IPv6 support. Link-local addresses included with /10 prefix. Pending V9/router validation. |
| `get_interfaces_counters` | `planned` | Formerly `display interface` | Explicit method entry exists and raises `NotImplementedError`; previous parser approach is deprecated and needs rewrite. |
| `get_lldp_neighbors` | `partial` | `display lldp neighbor-information verbose` | Existing implementation; V9/router validation needed. |
| `get_lldp_neighbors_detail` | `partial` | `display lldp neighbor-information verbose` | Existing implementation; profile-specific validation needed. |
| `get_environment` | `partial` | `display cpu-usage summary`, `display memory`, `display power`, `display fan`, `display environment` | Existing implementation; field coverage varies by chassis/box devices. |
| `get_arp_table` | `partial` | `display arp` | Existing implementation; VPN/VRF behavior needs more validation. |
| `get_mac_address_table` | `partial` | `display mac-address`, `display mac-address mac-move` | Existing implementation; switch-oriented. Router applicability unknown. |
| `get_vlans` | `partial` | `display vlan all` | Existing implementation; switch-oriented. Router applicability unknown. |
| `get_config` | `partial` | `display current-configuration`, `display saved-configuration` | Read-only config retrieval exists; sanitization and full mode are not implemented. |
| `get_route_to` | `partial` | `display ip routing-table`, `display ip routing-table {} verbose` | Non-verbose bulk + verbose per-destination. VRF support pending. `longer` param ignored. |
| `get_bgp_neighbors` | `partial` | `display bgp`, `display bgp peer ipv4` | IPv4 peers only. VRF-scoped peers pending. Some fields default to empty/-1. |
| `get_network_instances` | `partial` | `display ip vpn-instance`, `display ip vpn-instance instance-name {}` | Default instance + VPN instances. VRF detail interface list pending validation. |
| `get_bgp_config` | `planned` | TBD | Requires regex-based config parser for hierarchical text; TextFSM not suitable. |
| `get_bgp_neighbors_detail` | `partial` | `display bgp peer ipv4`, `display bgp peer {} verbose` | Per-peer iteration (expensive). Many fields default to zero/empty. IPv6 pending. |
| `get_ipv6_neighbors_table` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; required for IPv6 neighbor visibility. |
| `get_ntp_peers` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `get_ntp_servers` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `get_ntp_stats` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `get_snmp_information` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `get_users` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`. |
| `get_optics` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; requires transceiver command coverage by model. |
| `get_probes_config` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; requires NQA/probe command mapping. |
| `get_probes_results` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; requires NQA/probe command mapping. |
| `get_firewall_policies` | `unsupported` | N/A | Explicit method entry exists and raises `NotImplementedError`; firewalls are outside the target device scope. |

## Configuration Management Methods

| Method | Status | Current source | Notes |
| --- | --- | --- | --- |
| `load_replace_candidate` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; requires candidate strategy and safe rollback design. |
| `load_merge_candidate` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; merge-first design is likely, but must be validated. |
| `compare_config` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; diff reliability must be validated for V7/V9. |
| `commit_config` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; must define save behavior, failure handling, and privilege requirements. |
| `discard_config` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; depends on candidate strategy. |
| `rollback` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; requires validated archive/rollback behavior. |
| `confirm_commit` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; only if Comware behavior can be mapped safely. |
| `has_pending_commit` | `planned` | TBD | Explicit method entry exists and raises `NotImplementedError`; only if commit-confirm is implemented. |
| `confirm_commit` timeout helpers | `planned` | TBD | Only if commit-confirm is implemented. |

## H3C-Specific Extensions

| Method | Status | Current command/template | Notes |
| --- | --- | --- | --- |
| `get_irf_config` | `partial` | `display current-configuration configuration irf-port` | H3C extension, not a standard NAPALM getter. |
| `is_irf` | `partial` | `get_irf_config` | H3C extension, not a standard NAPALM getter. |
| `get_mac_address_move_table` | `partial` | `display mac-address mac-move` | H3C extension useful for switch operations. |
| `send_command` | `partial` | Netmiko `send_command` | Raw helper; not a standard NAPALM getter. |

## First Implementation Priorities

1. Build profile discovery for H3C Comware V7/V9 and switch/router role classification.
2. Refactor command selection into a registry before adding new getters.
3. Add parser fixtures from real production outputs before marking methods `supported`.
4. Rebuild `get_interfaces_counters` from dedicated parser/normalizer logic.
5. Add router-first getters such as `get_route_to`, `get_network_instances`, and BGP methods.
