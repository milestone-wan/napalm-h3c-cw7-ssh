# NAPALM Compliance Design

This document records the design constraints for evolving `napalm-h3c-cw7-ssh` into a broader H3C Comware driver while staying compatible with NAPALM third-party driver expectations.

## Goals and Scope

- Target H3C Comware V7 and V9 network devices.
- Target device roles are switches and routers.
- Firewalls are outside the supported device scope.
- SSH through Netmiko remains the current transport baseline.
- Existing driver entry point `h3c_comware` should remain backward compatible unless a future major release documents otherwise.
- New design work should align with NAPALM's `NetworkDriver` API and official getter/config method contracts.

## NAPALM References

Design and implementation should be checked against these NAPALM documents:

- NAPALM base driver API: https://napalm.readthedocs.io/en/latest/base.html
- Third-party/community driver guidance: https://napalm.readthedocs.io/en/latest/contributing/drivers.html
- Support matrix: https://napalm.readthedocs.io/en/latest/support/index.html
- Configuration workflow: https://napalm.readthedocs.io/en/latest/tutorials/changing_the_config.html
- Testing framework: https://napalm.readthedocs.io/en/latest/development/testing_framework.html

## API Compatibility Principles

- `ComwareDriver` must inherit from `napalm.base.base.NetworkDriver`.
- Public methods that implement NAPALM getters must return the structure and value types documented by NAPALM.
- H3C-specific helpers may be added, but they must not change the behavior of standard NAPALM methods.
- A method must not be documented as supported until its return schema is aligned with NAPALM and at least minimally validated.
- If a method cannot be supported for Comware switches/routers, it should be explicitly documented as unsupported with the reason.

## Return Structure Constraints

- Getter return values should use NAPALM field names and types, not raw TextFSM field names.
- Missing values should be normalized to the defaults expected by NAPALM for that method.
- Interface names should be canonicalized consistently.
- MAC addresses should be normalized with NAPALM helpers.
- Time and counter values should be converted to numeric types before returning.
- Raw CLI output should only be exposed through `cli()` or explicit helper methods, not mixed into standard getter schemas.

## Unsupported and Partial Methods

Use explicit behavior for methods that are not implemented or not fully supported:

- `planned`: method is in the roadmap but has no production-ready implementation yet.
- `partial`: method has code, but platform coverage, fields, parser stability, or validation is incomplete.
- `unsupported`: method is outside the H3C switch/router scope or cannot be implemented safely with the available Comware CLI behavior.
- `unknown`: current code or fixture coverage is not enough to decide support status.

Implementation should prefer clear exceptions or documented empty structures over silent `None` returns. Existing behavior may need compatibility handling during migration.

## Configuration Management Principles

NAPALM configuration workflows should be designed around the standard lifecycle:

1. `load_replace_candidate()` or `load_merge_candidate()`
2. `compare_config()`
3. `commit_config()` or `discard_config()`
4. Optional `rollback()` and commit-confirm related methods where Comware behavior can be validated

### Current implementation status

Merge and replace modes are implemented (`partial` in the support matrix):

- **Merge mode**: No device prerequisites. Candidate config stored locally, applied via `send_config_set()`, saved with `save force`. Error detection via `COMWARE_CONFIG_ERROR_PATTERNS` with automatic rollback on failure.
- **Replace mode**: Requires `archive configuration` enabled on the device. Candidate config transferred via SCP (`HPComwareFileTransfer`), applied via `configuration replace file`.
- **Rollback**: Archive-based (`configuration replace file`) when available; falls back to snapshot replay (idempotent, does not remove added commands).
- **Diff**: Python `difflib` — merge mode uses set-difference, replace mode uses unified diff. No native Comware diff command exists.

### Validated Comware-specific concerns

| Concern | Status | Notes |
|---------|--------|-------|
| Merge staging | Validated | Candidate stored locally; no device-side staging needed |
| Replace staging | Validated | Requires `archive configuration`; file transferred via SCP |
| Diff reliability | Partial | `difflib` works for text comparison; ordering/whitespace differences may cause noise |
| Commit atomicity | Partial | Merge is not atomic (commands apply one by one); replace is atomic via `configuration replace file` |
| Failure handling | Implemented | Error pattern detection + automatic rollback on merge failure |
| Privilege requirements | Documented | Requires system-view access and `save` privilege; replace also requires SCP and archive |
| Rollback | Partial | Archive-based: true rollback. Snapshot: idempotent replay only |

### Not yet validated / implemented

- `commit_config(revert_in=N)`: requires `configuration commit confirm-timeout` support, not available on all Comware V7 versions
- `confirm_commit()` / `has_pending_commit()`: depends on commit-confirm above

### Recently implemented

- `get_config(format="text")`: Implemented. Comware only supports text format; other values accepted but are no-ops.
- `get_config(sanitized=True)`: Implemented with H3C Comware-specific filter patterns (passwords, keys, SNMP communities).
- `get_config(full=True)`: Documented as no-op. Comware's ``display current-configuration`` always returns the full configuration.
- `ping`: Implemented with regex-based CLI output parsing. Supports all standard NAPALM parameters including ``source_interface`` and VRF.
- `traceroute`: Implemented with regex-based CLI output parsing. Supports VRF and source address.
- `get_users`: Improved — TextFSM template now supports both TABLE and DETAIL output formats. Config enrichment uses full `display current-configuration configuration local-user` instead of `| include local-user`. Multiple `authorization-attribute user-role` lines resolved to highest privilege level. Config command resolved via `users.config` CommandSpec.
- `send_command`: Channel-drain fallback strategy — prompt-based `send_command` → `read_channel_timing` drain (without re-sending) → reconnect on connection exception. Handles chassis/frame device long output and stale buffer issues. Commands are sent at most once in the normal path to avoid re-executing non-idempotent operations.
- `_discover_profile`: Uses `send_command_timing` directly for reliable `display version` on chassis devices. Includes regex fallback for model/version extraction when TextFSM fails.
- `display_fan.tpl`: Added `Fan Frame N State:` format support for chassis devices (S12504G).
- `display_local-user.tpl`: Added DETAIL state for verbose user output format.
- `display_version.tpl`: Refined pattern to `Comware\s+Software.*Version` to avoid false matches on `Release Version` lines in chassis output.
- `display_ipv6_interface.tpl`: Fixed link-local address matching — `IPv6 is enabled, link-local address is` line has no leading whitespace.
- `display_current-configuration_configuration_irf-port.tpl`: Fixed `irf-port` line matching — output lines have leading whitespace.
- `display_nqa_result.tpl`: Uses `Required` constraints and `-> Next.Record Start` to manage EOF duplicate records.
- Exception classes exported from `__init__.py`: `ComwareDriverError`, `ComwareParserError` (formerly `ParserError`; `ParserError` kept as backward-compatible alias), `UnsupportedCommandError`, `UnsupportedProfileError`, `ConfigManagementError`.
- `MANIFEST.in` cleaned up: removed stale `templates/*.j2` reference.

Until validated, configuration mutation methods should remain `planned` or `partial` in the support matrix.

## Profile-Aware Architecture

Future code should separate device facts from parser and command selection:

- `DeviceProfile`: brand, Comware major version, role, model, software version, and capabilities.
- `CommandSpec`: standard command, optional template name, parser key, supported profiles, fallback commands, and notes.
- Parser layer: transforms raw command output into extracted fields.
- Normalizer layer: transforms extracted fields into NAPALM-compliant schemas.

This profile-aware design is required to support V7/V9 and switch/router output differences without hardcoding all variants inside getter methods.

## Testing and Verification

- Offline parser tests should use real production command outputs as golden fixtures.
- Each fixture should record brand, Comware major version, device role, model, software version, command, and expected normalized output.
- Standard getter tests should validate NAPALM schema compatibility.
- Live-device tests should be opt-in and controlled by environment variables.
- A feature should not move to `supported` until parser output and normalized getter output are both verified.

## Documentation Rules

- Do not use absolute claims such as "fully supported" unless the claim is backed by tests and a documented support matrix entry.
- Document known platform, version, role, language, privilege, and parser limitations.
- Keep README files as entry points; keep detailed compliance and support status in `docs/`.
