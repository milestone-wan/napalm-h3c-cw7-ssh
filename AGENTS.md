# AGENTS.md — napalm-h3c-cw7-ssh Architecture Overview

## Project Overview

NAPALM third-party driver for H3C Comware V7/V9 network devices (switches and routers) over SSH. Implements the `NetworkDriver` interface from [NAPALM](https://github.com/napalm-automation/napalm).

- **PyPI package**: `napalm-h3c-comware`
- **Driver entry point**: `h3c_comware` (via `setup.py` entry_points)
- **Transport**: SSH via Netmiko (`hp_comware` device type)
- **Target devices**: H3C Comware V7/V9 switches and routers — firewalls are explicitly excluded
- **License**: Apache 2.0

**Config management**: Merge and replace modes are implemented (`partial`). Merge mode works on all devices; replace mode requires `archive configuration` enabled. `confirm_commit`/`has_pending_commit`/`revert_in` remain `planned`.

### Architecture Layers

```
ComwareDriver (inherits napalm.base.base.NetworkDriver)
  |
  +-- SSH transport: Netmiko HPComwareBase
  +-- Command registry: CommandSpec + CommandRegistry (profile-aware, integrated)
  +-- Device profiling: DeviceProfile + DeviceRole (auto-detected on open)
  +-- Parsing: TextFSM templates (.tpl) via napalm.base.helpers.textfsm_extractor
  +-- Config management: HPComwareFileTransfer (SCP), local candidate storage, difflib diffs
  +-- Exceptions: ComwareDriverError hierarchy (caught in getters and config methods)
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

```bash
python3 -m pytest tests/ -v                    # run all tests
python3 -m pytest tests/test_config_management.py -v  # config management only
```

Test categories:

- **Offline parser tests**: Use real production CLI output as golden fixtures. Each fixture records brand, Comware version, device role, model, software version, command, and expected normalized output.
- **Schema validation**: Getter return values must match NAPALM schemas.
- **Config management tests**: Mocked Netmiko device with `unittest.mock.MagicMock`. Tests cover merge/replace load, compare, commit, discard, rollback, error detection, and `HPComwareFileTransfer`.
- **Live-device tests**: Opt-in, controlled by environment variables.
- A getter should not be marked `supported` until both parser and normalized output are verified.

### Packaging

- `setup.py` reads dependencies from `requirements.txt` (only `napalm>=3.0.0`), version from `__init__.py`.
- `MANIFEST.in` includes `*.tpl` files — new templates are automatically packaged.
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

## Configuration Management Architecture

### Design

Comware has no native candidate configuration concept — changes in `system-view` take effect immediately. The NAPALM candidate config model is simulated by storing the candidate locally:

- **Candidate storage**: `self._candidate_config` (string in memory)
- **Mode tracking**: `self._config_replace` (bool), `self._loaded` (bool)
- **Rollback snapshot**: `self._pre_commit_config` (running config captured before commit)

### Merge mode workflow

```
load_merge_candidate(config=...)  → store locally, _config_replace=False
compare_config()                  → difflib set-difference: candidate lines not in running
commit_config()                   → snapshot running → send_config_set(commands) → check errors → save force
discard_config()                  → clear local state
rollback()                        → replay pre-commit snapshot (or archive-based replace)
```

### Replace mode workflow

```
load_replace_candidate(config=...) → store locally, _config_replace=True
compare_config()                   → difflib unified_diff: full running vs candidate
commit_config()                    → check archive → SCP transfer → configuration replace file → save force
rollback()                         → archive: configuration replace file; fallback: snapshot replay
```

### HPComwareFileTransfer

Custom `BaseFileTransfer` subclass adapting Netmiko's SCP handler to Comware CLI:

- `check_file_exists()`: uses `dir {fs}/{file}`
- `remote_md5()`: uses `md5sum {fs}/{file}`
- `enable_scp()` / `disable_scp()`: uses `scp server enable` / `undo scp server enable`
- `remote_space_available()`: parses `dir` output for free space

### Error detection

`COMWARE_CONFIG_ERROR_PATTERNS` — regex list of Comware inline error messages (`% Unrecognized command`, `% Ambiguous command`, etc.). Applied via `_check_config_errors()` after `send_config_set()`. On error, automatic rollback is attempted before raising `MergeConfigException`.

### Rollback strategies

| Strategy | Prerequisite | Behavior |
|----------|-------------|----------|
| Archive-based | `archive configuration` enabled | `configuration replace file` — true atomic rollback |
| Snapshot replay | None | Re-apply pre-commit config — idempotent but does NOT remove added commands |

The driver auto-detects archive support via `_check_archive_feature()` and degrades gracefully.

### Optional args

| Key | Default | Purpose |
|-----|---------|---------|
| `dest_file_system` | `flash:` | Remote filesystem for config file transfer |
| `candidate_cfg` | `candidate_config.txt` | Remote filename for candidate config |
| `rollback_cfg` | `rollback_config.txt` | Remote filename for rollback config |
| `resync_delay` | `0.3` | Delay (seconds) before prompt re-sync after timing-based reads |
| `is_alive_active_probe` | `False` | Send `display clock` to actively verify connection responsiveness |

### Not yet implemented

- `commit_config(revert_in=N)`: requires `configuration commit confirm-timeout` support validation
- `confirm_commit()` / `has_pending_commit()`: depends on commit-confirm above

## i18n / Chinese Output Handling

H3C devices in Chinese locale output Chinese status text. The driver sends `terminal language` during `open()` to force English output. This behavior is enabled by default and can be disabled via `optional_args={"force_english": False}`.

If `terminal language` fails (e.g., unsupported on some firmware), a warning is logged and the driver continues. In that case, status checks based on English keywords (`"up"`, `"normal"`, `"never"`, `"static"`) may silently produce wrong results on Chinese-locale devices.

## Connection & Timeout Management

- `self.timeout` is passed to Netmiko via `netmiko_optional_args` if not already specified by the user.
- `open()` performs: SSH connect -> force English output -> discover device profile.
- `send_command()` uses a channel-drain fallback strategy:
  1. **Primary**: `send_command` (prompt-based detection) — works for most devices and short outputs.
  2. **Drain**: `read_channel_timing` — when prompt detection returns empty, drain the already-sent command's output without re-sending. This avoids re-executing non-idempotent commands.
  3. **Last resort**: reconnect and retry — used only when `send_command` throws a connection exception (indicating the command may not have been sent at all).
- `_resync_prompt()` is called after channel drain to re-sync the session prompt via `find_prompt()`. Delay is configurable via `optional_args["resync_delay"]` (default 0.3s).
- `_discover_profile()` uses `send_command_timing` directly because `display version` on chassis devices produces extremely long output that breaks prompt detection.
- `_get_structured_output()` caches non-empty results per session — duplicate calls to the same command return cached data without re-sending to the device. Empty results are NOT cached to avoid poisoning the session cache from transient failures. Cache is cleared on `open()` and `_reconnect()`.
- `is_alive()` checks `self.device is None` and `self.device.is_alive()`. Optional active probe via `optional_args["is_alive_active_probe"]` sends `display clock` to verify responsiveness.
- `close()` clears all internal state (cache, candidate config, pre-commit snapshot) before closing the connection.
- `_reconnect()` re-executes `screen-length disable` and `force_english` (if configured), matching `open()` behavior.

## Chassis/Frame Device Handling

H3C chassis devices (e.g. S12504G, S125xx, S75xx) produce fundamentally different CLI output compared to box/standalone devices:

- **`display version`**: Output can exceed 15000 characters with per-board (LPU/MPU/NPU) details. The version header (`H3C Comware Software...`) appears at the **end** of the output, after all board information. This causes `send_command` to truncate or return empty.
- **`display fan`**: Uses `Fan Frame N State: Normal` format instead of `Fan N` or `Fan-tray N`.
- **`screen-length disable`**: Not supported on some chassis firmware — the driver logs a warning and continues.
- **Prompt format**: Chassis devices may use `<hostname>` (angle brackets) instead of `[hostname]` (square brackets) for user-view prompts.

The driver handles these differences through:
- `read_channel_timing` drain fallback in `send_command()` when prompt detection returns empty
- Multi-state TextFSM templates (e.g. `display_fan.tpl` supports `Fan Frame` format)
- Regex fallback in `_discover_profile()` when TextFSM parsing fails

## Known Code Issues

1. **`get_environment()` serial commands** — sends 5 commands with no recovery if connection drops mid-way (mitigated by `send_command` reconnect logic, but partial data loss is still possible).
2. **Long-running sessions** — keeping multiple SSH connections alive for extended periods (e.g. during full test suite runs) may cause connections to become unstable. The `send_command` reconnect mechanism mitigates this but does not eliminate it.

## Recent Bug Fixes

The following issues were identified and fixed:

1. **`send_command` command re-execution (CRITICAL)** — The three-tier fallback strategy (`send_command` → `send_command_timing` → reconnect) could re-send the same command up to 3 times. For non-idempotent commands (config changes, reboots), this was dangerous. **Fix**: When `send_command` returns empty, use `read_channel_timing()` to drain the already-sent command's output without re-sending. Only reconnect on actual connection exceptions.
2. **Empty results cached permanently** — `_get_structured_output()` cached empty TextFSM results `[]`, poisoning the cache for the entire session if the first call failed due to a transient issue. **Fix**: Only cache non-empty results.
3. **`_reconnect()` missing `screen-length disable`** — After reconnect, long output could be truncated by `--More--` pagination. **Fix**: Added `screen-length disable` call in `_reconnect()`, matching `open()`.
4. **`_get_temperature()` threshold=0 false alerts** — When alert/critical threshold was 0 (not configured), any temperature >= 0 triggered false alerts. **Fix**: Only compare when threshold > 0.
5. **Environment key naming inconsistency** — `_get_power` and `_get_temperature` used lowercase keys (`"slot"`, `"chassis"`) while `_get_cpu` and `_get_fan` used capitalized keys (`"Slot"`, `"Chassis"`). **Fix**: Standardized to capitalized format.
6. **`_resync_prompt()` hardcoded 1-second delay** — Accumulated in batch operations. **Fix**: Configurable via `optional_args["resync_delay"]`, default reduced to 0.3s.
7. **`ParserError` name conflict** — Generic name could conflict with Python built-in exceptions. **Fix**: Renamed to `ComwareParserError` with backward-compatible `ParserError` alias.
8. **`get_facts()` single try block** — One command failure aborted all remaining data collection. **Fix**: Split into 4 independent try blocks (version/hostname/interfaces/serial).
9. **`close()` no state cleanup** — Cache and config state persisted after close. **Fix**: Clear all internal state on close.
10. **`is_alive()` passive-only check** — Could report stale connections as alive. **Fix**: Added optional active probe via `optional_args["is_alive_active_probe"]` (sends `display clock`).

## Current Refactor Status

The profile-aware architecture is now integrated:

- `commands.py`: `CommandSpec` + `CommandRegistry` — all getters use `self._get_command(key)` to resolve commands. Includes `users.config` for local-user config enrichment.
- `profiles.py`: `DeviceProfile`, `DeviceRole`, `ComwareMajorVersion` — `_discover_profile()` is called during `open()`, populating `self.profile`.
- `exceptions.py`: `ComwareDriverError` hierarchy — `ComwareParserError` (formerly `ParserError`) is raised by `_get_structured_output()` and caught in all getters. `ParserError` is kept as a backward-compatible alias. All exceptions are exported from `__init__.py`.

Remaining refactor work:
- Add V9/router-specific `CommandSpec` variants when output differences are confirmed

## Support Matrix Summary

All currently implemented getters are `partial` — they have been validated on V7 switches (including chassis devices like S12504G) but need V9/router validation. See `docs/getters-support-matrix.md` for the full matrix. Key implemented getters: `get_facts`, `get_interfaces`, `get_interfaces_ip` (IPv4 + IPv6), `get_lldp_neighbors`, `get_lldp_neighbors_detail`, `get_environment`, `get_arp_table`, `get_mac_address_table`, `get_vlans`, `get_config`, `get_route_to`, `get_network_instances`, `get_bgp_neighbors`, `get_bgp_neighbors_detail`, `get_bgp_config`, `get_ntp_stats`, `get_ntp_peers`, `get_ntp_servers`, `get_snmp_information`, `get_users`, `get_optics`, `get_probes_config`, `get_probes_results`, `get_ipv6_neighbors_table`, `get_interfaces_counters`. H3C extensions: `get_irf_config`, `is_irf`, `get_mac_address_move_table`. Configuration management methods are `partial` (merge + replace modes implemented; commit-confirm `planned`).

### Validated device models

| Model | Form Factor | Comware Version | Role |
|-------|-------------|-----------------|------|
| S6805-54HT | Box/IRF | V7 (7.1.070, Release 6616P01) | Switch |
| S12504G-AF | Chassis/Frame | V7 (7.1.070, Release 7634P11) | Switch |
| S9850-32H | Box/IRF | V7 (Release 6635) | Switch |
| S5130S-52S-HI | Standalone | V7 (Release 6343P08) | Switch |
| S6520X-54QC-EI | Box/IRF | V7 (Release 6530P02) | Switch |
