"""Unit tests for napalm_h3c_comware.commands."""

import pytest

from napalm_h3c_comware.commands import (
    COMMON_VERSIONS,
    SWITCH_AND_ROUTER,
    SWITCH_ONLY,
    CommandRegistry,
    CommandSpec,
    default_command_registry,
)
from napalm_h3c_comware.exceptions import UnsupportedCommandError
from napalm_h3c_comware.profiles import ComwareMajorVersion, DeviceProfile, DeviceRole


def _make_profile(version=ComwareMajorVersion.V7, role=DeviceRole.SWITCH):
    return DeviceProfile(major_version=version, role=role)


class TestCommandSpec:
    def test_supports_matching_profile(self):
        spec = CommandSpec(
            key="test", command="display test",
            versions=COMMON_VERSIONS, roles=SWITCH_AND_ROUTER,
        )
        assert spec.supports(_make_profile()) is True

    def test_supports_excludes_wrong_role(self):
        spec = CommandSpec(
            key="test", command="display test",
            versions=COMMON_VERSIONS, roles=SWITCH_ONLY,
        )
        router_profile = _make_profile(role=DeviceRole.ROUTER)
        assert spec.supports(router_profile) is False

    def test_supports_empty_constraints_match_all(self):
        spec = CommandSpec(key="test", command="display test")
        assert spec.supports(_make_profile()) is True

    def test_effective_template_name_explicit(self):
        spec = CommandSpec(key="test", command="display test", template_name="custom")
        assert spec.effective_template_name == "custom"

    def test_effective_template_name_derived(self):
        spec = CommandSpec(key="test", command="display ip routing-table")
        assert spec.effective_template_name == "display_ip_routing-table"

    def test_frozen(self):
        spec = CommandSpec(key="test", command="display test")
        with pytest.raises(AttributeError):
            spec.key = "other"


class TestCommandRegistry:
    def test_register_and_get(self):
        registry = CommandRegistry()
        spec = CommandSpec(key="test", command="display test")
        registry.register(spec)
        assert registry.get("test") == (spec,)

    def test_get_missing_key(self):
        registry = CommandRegistry()
        assert registry.get("missing") == ()

    def test_resolve_matching_spec(self):
        spec = CommandSpec(
            key="test", command="display test",
            versions=COMMON_VERSIONS, roles=SWITCH_AND_ROUTER,
        )
        registry = CommandRegistry([spec])
        resolved = registry.resolve("test", _make_profile())
        assert resolved.command == "display test"

    def test_resolve_no_match_raises(self):
        spec = CommandSpec(
            key="test", command="display test",
            versions=COMMON_VERSIONS, roles=SWITCH_ONLY,
        )
        registry = CommandRegistry([spec])
        with pytest.raises(UnsupportedCommandError):
            registry.resolve("test", _make_profile(role=DeviceRole.ROUTER))

    def test_resolve_missing_key_raises(self):
        registry = CommandRegistry()
        with pytest.raises(UnsupportedCommandError):
            registry.resolve("missing", _make_profile())

    def test_multiple_specs_picks_first_match(self):
        spec_switch = CommandSpec(
            key="test", command="display test switch",
            versions=COMMON_VERSIONS, roles=SWITCH_ONLY,
        )
        spec_both = CommandSpec(
            key="test", command="display test both",
            versions=COMMON_VERSIONS, roles=SWITCH_AND_ROUTER,
        )
        registry = CommandRegistry([spec_switch, spec_both])
        resolved = registry.resolve("test", _make_profile())
        assert resolved.command == "display test switch"


class TestDefaultCommandRegistry:
    def test_registry_has_specs(self):
        registry = default_command_registry()
        assert len(registry.get("facts.version")) > 0

    def test_route_table_registered(self):
        registry = default_command_registry()
        assert len(registry.get("route.table")) > 0

    def test_bgp_peer_registered(self):
        registry = default_command_registry()
        assert len(registry.get("bgp.peer")) > 0

    def test_ipv6_interface_registered(self):
        registry = default_command_registry()
        assert len(registry.get("interfaces.ipv6")) > 0

    def test_vpn_instance_registered(self):
        registry = default_command_registry()
        assert len(registry.get("vpn.instance")) > 0

    def test_switch_only_commands_excluded_for_router(self):
        registry = default_command_registry()
        router_profile = _make_profile(role=DeviceRole.ROUTER)
        with pytest.raises(UnsupportedCommandError):
            registry.resolve("vlans", router_profile)
