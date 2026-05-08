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

The design must document these Comware-specific concerns before enabling production configuration changes:

- Whether merge and replace operations can be safely staged.
- How diffs are generated and whether they are reliable across V7/V9.
- Whether commit, discard, rollback, and save behavior can be made atomic.
- Required privilege level and command authorization.
- Failure handling when a command is rejected halfway through a candidate configuration.

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
