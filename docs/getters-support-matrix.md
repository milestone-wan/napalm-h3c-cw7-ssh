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
| `open` | `partial` | Netmiko `hp_comware` | Current transport is SSH/Netmiko; profile discovery uses `send_command_timing` for chassis device compatibility. |
| `close` | `partial` | Netmiko close | Session close with state cleanup (cache, config state cleared). |
| `is_alive` | `partial` | Netmiko `is_alive()` | Passive check by default. Optional active probe via `optional_args["is_alive_active_probe"]` sends `display clock` to verify responsiveness. |
| `cli` | `partial` | Raw Netmiko commands | Useful helper; command authorization and sanitization are caller responsibility. |
| `ping` | `partial` | Regex-based CLI parsing | Implemented with `source_interface`, VRF, and all standard parameters. Pending V9/router validation. |
| `traceroute` | `partial` | Regex-based CLI parsing | Implemented with VRF and source support. Pending V9/router validation. |
| `load_template` | `planned` | TBD | Inherited from NAPALM base until template strategy is designed. |

## Standard Getters

| Getter | Status | Current command/template | Notes |
| --- | --- | --- | --- |
| `get_facts` | `partial` | `display version`, `display interface`, `display device manuinfo` | Existing V7-oriented implementation; V9/router validation needed. Independent try blocks for each data source — partial data returned when one command fails. |
| `get_interfaces` | `partial` | `display interface` | Existing implementation; parser is known to be broad and needs redesign for counters/output variants. |
| `get_interfaces_ip` | `partial` | `display ip interface`, `display ipv6 interface` | IPv4 + IPv6 support. Link-local addresses included with /10 prefix. Pending V9/router validation. |
| `get_interfaces_counters` | `partial` | `display interface` (TextFSM `display_interface_counters.tpl`) | TextFSM-based counter parsing of Input/Output sections. Pending V9/router validation. |
| `get_lldp_neighbors` | `partial` | `display lldp neighbor-information verbose` | Existing implementation; V9/router validation needed. |
| `get_lldp_neighbors_detail` | `partial` | `display lldp neighbor-information verbose` | Existing implementation; profile-specific validation needed. |
| `get_environment` | `partial` | `display cpu-usage summary`, `display memory`, `display power`, `display fan`, `display environment` | Existing implementation; field coverage varies by chassis/box devices. Chassis devices (S12504G) validated with `Fan Frame` format support. Environment keys use capitalized format (`Slot`, `Chassis`, `Power`, `Fan`, `Sensor`). Temperature thresholds of 0 (not configured) no longer trigger false alerts. |
| `get_arp_table` | `partial` | `display arp` | Existing implementation; VPN/VRF behavior needs more validation. |
| `get_mac_address_table` | `partial` | `display mac-address`, `display mac-address mac-move` | Existing implementation; switch-oriented. Router applicability unknown. |
| `get_vlans` | `partial` | `display vlan all` | Existing implementation; switch-oriented. Router applicability unknown. |
| `get_config` | `partial` | `display current-configuration`, `display saved-configuration` | Read-only config retrieval; sanitization implemented with H3C-specific filters; `full` mode documented as no-op (Comware always returns full config). `read_timeout=120` for long outputs on chassis devices. |
| `get_route_to` | `partial` | `display ip routing-table`, `display ip routing-table {} verbose` | Non-verbose bulk + verbose per-destination. VRF support pending. `longer` param ignored. |
| `get_bgp_neighbors` | `partial` | `display bgp`, `display bgp peer ipv4` | IPv4 peers only. VRF-scoped peers pending. Some fields default to empty/-1. |
| `get_network_instances` | `partial` | `display ip vpn-instance`, `display ip vpn-instance instance-name {}` | Default instance + VPN instances. VRF detail interface list pending validation. |
| `get_bgp_config` | `partial` | `display current-configuration configuration bgp` (regex) | Multi-pass regex parsing of BGP config. Peer groups and individual peers supported. VRF-scoped BGP pending. |
| `get_bgp_neighbors_detail` | `partial` | `display bgp peer ipv4`, `display bgp peer {} verbose` | Per-peer iteration (expensive). Many fields default to zero/empty. IPv6 pending. |
| `get_ipv6_neighbors_table` | `partial` | `display ipv6 neighbors` (TextFSM) | TextFSM-based parsing. Pending V9/router validation. |
| `get_ntp_peers` | `partial` | Delegates to `get_ntp_stats` | Extracts peer addresses from NTP stats. |
| `get_ntp_servers` | `partial` | `display current-configuration \| include ntp-service` (regex) | Regex config parsing. Supports version, source, VRF. |
| `get_ntp_stats` | `partial` | `display ntp-service sessions` (TextFSM) | TextFSM-based key-value parsing. Pending real device output validation. |
| `get_snmp_information` | `partial` | `display snmp-agent sys-info` (TextFSM) + community config (TextFSM) | Dual-command: sys-info TextFSM + community config TextFSM parsing. |
| `get_users` | `partial` | `display local-user` (TextFSM) + `display current-configuration configuration local-user` (regex) | TextFSM supports both TABLE and DETAIL output formats. Config enrichment for level/password via full local-user config section (resolved via `users.config` CommandSpec). Multiple `authorization-attribute user-role` lines resolved to highest privilege. |
| `get_optics` | `partial` | `display transceiver diagnosis interface` (TextFSM) | TextFSM-based parsing. Only instant power/bias values; avg/min/max default to 0.0. Not all models support diagnostics. |
| `get_probes_config` | `partial` | `display current-configuration \| include nqa` (TextFSM) | TextFSM state-machine parsing of NQA config blocks. |
| `get_probes_results` | `partial` | `display nqa result` (TextFSM) | TextFSM-based key-value parsing. target/source fields empty (not in output). Duplicate records from EOF auto-emit are deduplicated by dict key in getter. |
| `get_firewall_policies` | `unsupported` | N/A | Explicit method entry exists and raises `NotImplementedError`; firewalls are outside the target device scope. |

## Configuration Management Methods

| Method | Status | Current source | Notes |
| --- | --- | --- | --- |
| `load_replace_candidate` | `partial` | Local string storage | Stores candidate config locally; commit requires `archive configuration` enabled on device. |
| `load_merge_candidate` | `partial` | Local string storage | Stores candidate config locally; commit applies via `send_config_set`. |
| `compare_config` | `partial` | Python `difflib` | Merge mode: set-difference of candidate vs running. Replace mode: unified diff. No native Comware diff command. |
| `commit_config` | `partial` | `send_config_set` (merge), `configuration replace file` (replace) | Merge: applies commands + `save force`. Replace: requires archive + SCP file transfer + `configuration replace file`. `revert_in` not yet supported. |
| `discard_config` | `partial` | Local state clear | Clears locally stored candidate; no device interaction. |
| `rollback` | `partial` | Archive-based or snapshot replay | Archive enabled: `configuration replace file` with pre-commit snapshot. Fallback: idempotent replay of pre-commit config (does NOT remove added commands). |
| `confirm_commit` | `planned` | TBD | Raises `NotImplementedError`; requires `configuration commit confirm-timeout` support validation. |
| `has_pending_commit` | `planned` | TBD | Returns `False`; requires commit-confirm implementation. |

### Configuration Management Prerequisites

- **Merge mode**: No device prerequisites. Works on any Comware V7/V9 device.
- **Replace mode**: Requires `archive configuration` enabled on the device. Enable with: `archive configuration location <dir> max <n>`. Also requires SCP server enabled for file transfer.
- **Rollback**: Archive-based rollback (recommended) requires `archive configuration`. Snapshot-based rollback (fallback) works without prerequisites but cannot remove added commands.
- **Optional args**: `dest_file_system` (default: `flash:`), `candidate_cfg` (default: `candidate_config.txt`), `rollback_cfg` (default: `rollback_config.txt`), `resync_delay` (default: `0.3` seconds, delay before prompt re-sync after timing-based reads), `is_alive_active_probe` (default: `False`, send `display clock` to verify connection responsiveness).

## H3C-Specific Extensions

| Method | Status | Current command/template | Notes |
| --- | --- | --- | --- |
| `get_irf_config` | `partial` | `display current-configuration configuration irf-port` | H3C extension, not a standard NAPALM getter. |
| `is_irf` | `partial` | `get_irf_config` | H3C extension, not a standard NAPALM getter. |
| `get_mac_address_move_table` | `partial` | `display mac-address mac-move` | H3C extension useful for switch operations. |
| `send_command` | `partial` | Netmiko `send_command` + `read_channel_timing` drain | Channel-drain fallback: prompt-based `send_command` → `read_channel_timing` drain (no re-send) → reconnect on connection exception. Commands sent at most once in normal path to avoid re-executing non-idempotent operations. |

## Implementation Priorities

1. ~~Build profile discovery for H3C Comware V7/V9 and switch/router role classification.~~ Done.
2. ~~Refactor command selection into a registry before adding new getters.~~ Done.
3. Add parser fixtures from real production outputs before marking methods `supported`.
4. ~~Rebuild `get_interfaces_counters` from dedicated parser/normalizer logic.~~ Done — uses `display_interface_counters.tpl` TextFSM template.
5. ~~Add router-first getters such as `get_route_to`, `get_network_instances`, and BGP methods.~~ Done.
6. Add V9/router-specific `CommandSpec` variants when output differences are confirmed.
7. Validate all getters on real V9 and router devices to move from `partial` to `supported`.

## Validated Device Models

Live-device testing has been performed on the following H3C Comware V7 switch models. All standard getters pass without errors on these devices.

| Model | Form Factor | Comware Version | Role | Notes |
|-------|-------------|-----------------|------|-------|
| S6805-54HT | Box/IRF | V7 (7.1.070, Release 6616P01) | Switch | Primary test device |
| S12504G-AF | Chassis/Frame | V7 (7.1.070, Release 7634P11) | Switch | Chassis device; requires `send_command_timing` fallback for long outputs |
| S9850-32H | Box/IRF | V7 (Release 6635) | Switch | |
| S5130S-52S-HI | Standalone | V7 (Release 6343P08) | Switch | `terminal language` not supported |
| S6520X-54QC-EI | Box/IRF | V7 (Release 6530P02) | Switch | |

### Chassis device specific notes

- **S12504G-AF**: `display version` output exceeds 15000 characters with per-board (LPU/MPU/NPU) details. The version header appears at the end of the output. `screen-length disable` is not supported. `display fan` uses `Fan Frame N State: Normal` format.
- All chassis-specific issues are handled by the driver's `read_channel_timing` drain fallback and multi-state TextFSM templates.
