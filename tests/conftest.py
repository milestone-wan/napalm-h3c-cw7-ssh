"""Shared test fixtures and utilities."""

import os
import re

import pytest
import yaml

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

LIVE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "live_devices.yaml")


# ---------------------------------------------------------------------------
# Unit test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


def read_fixture(name):
    """Read a fixture file from tests/fixtures/ and return its content."""
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Live device test infrastructure
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    """Add CLI options for live device testing."""
    group = parser.getgroup("live", "Live device testing")
    group.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Enable live device integration tests",
    )
    group.addoption(
        "--live-device",
        default=None,
        help="Only test the device with this name (from live_devices.yaml)",
    )
    group.addoption(
        "--live-tag",
        default=None,
        help="Only test devices matching this tag (from live_devices.yaml)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --live is specified."""
    if config.getoption("--live", default=False):
        return
    skip_live = pytest.mark.skip(reason="needs --live flag to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def _load_live_devices():
    """Load device list from live_devices.yaml. Returns empty list if missing."""
    if not os.path.exists(LIVE_CONFIG_PATH):
        return []
    with open(LIVE_CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("devices", []) if data else []


def _filter_devices(devices, device_name=None, tag=None):
    """Filter devices by name or tag."""
    if device_name:
        devices = [d for d in devices if d.get("name") == device_name]
    if tag:
        devices = [d for d in devices if tag in d.get("tags", [])]
    return devices


def _sanitize_output(text):
    """Redact sensitive information from output for logging."""
    # Replace IP addresses: keep last octet visible
    text = re.sub(
        r"\b(\d{1,3})\.\d{1,3}\.\d{1,3}\.(\d{1,3})\b",
        lambda m: f"{m.group(1)}.*.*.{m.group(2)}",
        text,
    )
    return text


@pytest.fixture(scope="session")
def live_devices(request):
    """Session-scoped fixture providing the list of live device configs."""
    if not request.config.getoption("--live", default=False):
        pytest.skip("needs --live flag")
    devices = _load_live_devices()
    if not devices:
        pytest.skip("live_devices.yaml not found or empty")
    device_name = request.config.getoption("--live-device", default=None)
    tag = request.config.getoption("--live-tag", default=None)
    devices = _filter_devices(devices, device_name=device_name, tag=tag)
    if not devices:
        pytest.skip("no devices match the given --live-device / --live-tag filter")
    return devices


@pytest.fixture(scope="session")
def live_device_drivers(live_devices):
    """Session-scoped fixture: open and return {name: driver} for all matched devices.

    Devices that fail to connect are skipped gracefully.
    """
    from napalm import get_network_driver

    driver_cls = get_network_driver("h3c_comware")
    drivers = {}
    for dev in live_devices:
        name = dev["name"]
        optional_args = {}
        if dev.get("port") and dev["port"] != 22:
            optional_args["port"] = dev["port"]
        d = driver_cls(
            hostname=dev["host"],
            username=dev["username"],
            password=dev["password"],
            optional_args=optional_args if optional_args else None,
        )
        try:
            d.open()
            drivers[name] = d
        except Exception as e:
            print(f"SKIP {name}: connection failed: {e}")
    if not drivers:
        pytest.skip("no devices could be connected")
    yield drivers
    # Teardown: close all connections
    for d in drivers.values():
        try:
            d.close()
        except Exception:
            pass


@pytest.fixture
def live_device(request, live_device_drivers):
    """Fixture providing a single (name, driver) pair, parameterized across devices."""
    # This fixture is used indirectly via live_device_drivers parametrize
    # Individual tests should use live_device_drivers directly
    return live_device_drivers
