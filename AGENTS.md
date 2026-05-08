# AGENTS.md — napalm-h3c-cw7-ssh Architecture Overview

## Project Overview

NAPALM third-party driver for H3C Comware V7/V9 network devices (switches and routers) over SSH. Implements the `NetworkDriver` interface from [NAPALM](https://github.com/napalm-automation/napalm).

- **PyPI package**: `napalm-h3c-comware`
- **Driver entry point**: `h3c_comware` (via `setup.py` entry_points)
- **Transport**: SSH via Netmiko (`hp_comware` device type)
- **Target devices**: H3C Comware V7/V9 switches and routers — firewalls are explicitly excluded
- **License**: Apache 2.0

**Config management**: All mutation methods (`load_replace_candidate`, `commit_config`, etc.) raise `NotImplementedError`. Do not enable them until safe rollback and failure handling are validated.

### Architecture Layers

```
ComwareDriver (inherits napalm.base.base.NetworkDriver)
  |
  +-- SSH transport: Netmiko HPComwareBase
  +-- Command registry: CommandSpec + CommandRegistry (profile-aware, integrated)
  +-- Device profiling: DeviceProfile + DeviceRole (auto-detected on open)
  +-- Parsing: TextFSM templates (.tpl) via napalm.base.helpers.textfsm_extractor
  +-- Exceptions: ComwareDriverError hierarchy (caught in getters)
  +-- Logging: module-level logger with DEBUG/INFO/WARNING/ERROR
```

## Build & Commands

### Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install -r requirements-dev.txt   # twine, setuptools, build
```

### Release

```bash
# 1. Bump version in napalm_h3c_comware/__init__.py
# 2. Tag and push
git tag -a <version> -m <comment>
git push origin --tags
# 3. Build and publish
python -m build && python -m twine upload dist/*
```

### Testing

No test framework configured. The intended approach (from `docs/napalm-compliance.md`):

- **Offline parser tests**: Use real production CLI output as golden fixtures. Each fixture records brand, Comware version, device role, model, software version, command, and expected normalized output.
- **Schema validation**: Getter return values must match NAPALM schemas.
- **Live-device tests**: Opt-in, controlled by environment variables.
- A getter should not be marked `supported` until both parser and normalized output are verified.

### Packaging

- `setup.py` reads dependencies from `requirements.txt` (only `napalm>=3.0.0`), version from `__init__.py`.
- `MANIFEST.in` includes `*.tpl` and `*.j2` files — new templates are automatically packaged.
- No `pyproject.toml`, no CI/CD, no pre-commit hooks.

## Code Style

- **Python**: 3.6+ (declared in setup.py)
- **Formatting**: No linter/formatter configured. Follow PEP 8.
- **Naming**: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- **Type hints**: Required in new modules. Use `typing` module (`Optional`, `Dict`, `List`, `FrozenSet`).
- **Immutability**: Use `@dataclass(frozen=True)` for value objects (`CommandSpec`, `DeviceProfile`).
- **Enums**: Use `str, Enum` or `IntEnum` for type-safe enumerations.
- **Imports**: Standard library -> third-party -> local modules. Absolute imports only.
- **Comments**: Mixed English and Chinese.
- **License headers**: Every source file has Apache 2.0 copyright + license header.

## Data Flow & Parsing Pipeline

All getters follow a 3-layer pipeline:

```
CLI command string (from CommandRegistry)
  -> Netmiko send_command() -> raw text
  -> textfsm_extractor(template_name, raw_text) -> list of dicts
  -> getter method normalization -> NAPALM schema dict
```

### Central methods

**`_get_command(key)`** — Resolves a command string from the registry for the current device profile. Falls back to first matching spec if profile is not yet detected.

**`_get_structured_output(command, template_name)`** — Sends command, parses output with TextFSM. Raises `ParserError` on parse failure, logs WARNING on empty results.

- If `template_name` is `None`, derives it by joining command words with underscores: `"display version"` -> `"display_version"` -> `display_version.tpl`
- Hyphens in CLI commands are **preserved** in template names: `"display cpu-usage summary"` -> `display_cpu-usage_summary.tpl`
- TextFSM field names are `UPPER_SNAKE_CASE` in templates but appear as `lower_snake_case` keys in Python dicts (automatic).

### Key helper: `parse_null(value, default, func)`

Converts `None` or empty strings to default values before applying an optional transform. Standard pattern for handling missing TextFSM fields:

```python
speed = parse_null(speed, -1, int)           # "" or None -> -1
mac_address = parse_null(mac_address, "unknown", mac)  # "" or None -> "unknown"
```

### Field access pattern

All getters use `.get("field", default)` instead of `itemgetter()`. This prevents `KeyError` when TextFSM templates miss a field. Each getter is wrapped in `try/except (KeyError, AttributeError, ParserError)` to return NAPALM defaults on partial failure.

## TextFSM Template Design

Templates live in `napalm_h3c_comware/utils/textfsm_templates/`. H3C Comware devices produce structurally different CLI output depending on form factor:

| Form Factor | Example Models | Output Characteristic |
|---|---|---|
| Standalone (单机) | Low-end fixed switches | No `Slot`/`Chassis` prefix |
| Box/IRF (盒式) | S68xx, S51xx, S55xx | `Slot N` prefix |
| Chassis/Frame (框式) | S125xx, S75xx | `Chassis N Slot M` prefix |

### Three strategies for form factor handling

**Strategy 1: Multi-state machines** (`display_cpu-usage_summary.tpl`, `display_fan.tpl`, `display_power.tpl`, `display_environment.tpl`)

The `Start` state inspects the first data line and routes to the appropriate state:
- `SINGLE_DEVICE` — standalone/low-end (no slot/chassis prefix)
- `NORMAL_DEVICE` — box devices with IRF (slot prefix only)
- `CHASSIS_DEVICE` — chassis/frame devices (chassis + slot prefix)
- `DEVELOP_TEST` — dev/test firmware output format (in `display_fan.tpl`)

**Strategy 2: Optional regex groups** (`display_memory.tpl`)

Single state with optional capture: `(Chassis\s+${CHASSIS})?` — the `Chassis` group is empty for box devices.

**Strategy 3: Filldown + Required** (`display_device_manuinfo.tpl`)

`Value Filldown CHASSIS` persists the chassis ID across records. `Value Required` prevents emitting incomplete records.

### Other template patterns

- `display_lldp_neighbor-information_verbose.tpl`: Uses `Continue` for multi-line system descriptions and `-> EOF` for early termination when LLDP is not running.
- `display_vlan_all.tpl`: Uses `Continue.Record` to emit the previous record before starting a new VLAN block.

## Adding a New Getter

1. **Create `.tpl` template** in `napalm_h3c_comware/utils/textfsm_templates/`. Name by CLI command with spaces -> underscores, hyphens preserved. Choose a form-factor strategy from above.
2. **Register a `CommandSpec`** in `commands.py` `DEFAULT_COMMAND_SPECS`. Set `key`, `getter`, `command`, `versions`, `roles`. Set `template_name` only if it differs from the command-derived name.
3. **Implement the getter** on `ComwareDriver` in `comware.py`. Use `self._get_command(key)` to resolve the command, then `self._get_structured_output(command)` to parse.
4. **Normalize TextFSM output** to NAPALM schema using `.get("field", default)` pattern. Handle form-factor differences by checking optional `chassis`/`slot` fields. Wrap in `try/except (KeyError, AttributeError, ParserError)`.
5. **Export if needed**: Add H3C-specific extensions to `__all__` in `__init__.py` and to the support matrix in `docs/`.
6. **No MANIFEST.in changes needed**: `*.tpl` files are already included.

## i18n / Chinese Output Handling

H3C devices in Chinese locale output Chinese status text. The driver sends `terminal language` during `open()` to force English output. This behavior is enabled by default and can be disabled via `optional_args={"force_english": False}`.

If `terminal language` fails (e.g., unsupported on some firmware), a warning is logged and the driver continues. In that case, status checks based on English keywords (`"up"`, `"normal"`, `"never"`, `"static"`) may silently produce wrong results on Chinese-locale devices.

## Connection & Timeout Management

- `self.timeout` is passed to Netmiko via `netmiko_optional_args` if not already specified by the user.
- `open()` performs: SSH connect -> force English output -> discover device profile.
- `send_command()` automatically attempts one reconnect+retry on failure. On reconnect, the command cache is cleared and English output is re-forced.
- `_get_structured_output()` caches results per session — duplicate calls to the same command return cached data without re-sending to the device. Cache is cleared on `open()` and `_reconnect()`.
- `is_alive()` checks `self.device is None` and `self.device.is_alive()`.

## Known Code Issues

1. **`get_environment()` serial commands** — sends 5 commands with no recovery if connection drops mid-way (mitigated by `send_command` retry logic, but partial data loss is still possible).

## Current Refactor Status

The profile-aware architecture is now integrated:

- `commands.py`: `CommandSpec` + `CommandRegistry` — all getters use `self._get_command(key)` to resolve commands.
- `profiles.py`: `DeviceProfile`, `DeviceRole`, `ComwareMajorVersion` — `_discover_profile()` is called during `open()`, populating `self.profile`.
- `exceptions.py`: `ComwareDriverError` hierarchy — `ParserError` is raised by `_get_structured_output()` and caught in all getters.

Remaining refactor work:
- Add V9/router-specific `CommandSpec` variants when output differences are confirmed

## Support Matrix Summary

All currently implemented getters are `partial` — they work for V7 switches but need V9/router validation. See `docs/getters-support-matrix.md` for the full matrix. Key implemented getters: `get_facts`, `get_interfaces`, `get_interfaces_ip` (IPv4 only), `get_lldp_neighbors`, `get_lldp_neighbors_detail`, `get_environment`, `get_arp_table`, `get_mac_address_table`, `get_vlans`, `get_config`. Configuration management methods are all `planned`.
