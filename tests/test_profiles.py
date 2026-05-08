"""Unit tests for napalm_h3c_comware.profiles."""

import pytest

from napalm_h3c_comware.exceptions import UnsupportedProfileError
from napalm_h3c_comware.profiles import (
    ComwareMajorVersion,
    DeviceProfile,
    DeviceRole,
    build_device_profile,
    classify_device_role,
    detect_comware_major_version,
)


class TestDetectComwareMajorVersion:
    def test_v7_from_version_string(self):
        text = "Comware Software, Version 7.1.070"
        assert detect_comware_major_version(text) == ComwareMajorVersion.V7

    def test_v9_from_version_string(self):
        text = "Comware Software, Version 9.0.021"
        assert detect_comware_major_version(text) == ComwareMajorVersion.V9

    def test_empty_string(self):
        assert detect_comware_major_version("") is None

    def test_none_input(self):
        assert detect_comware_major_version(None) is None

    def test_unknown_version(self):
        assert detect_comware_major_version("Some other text") is None


class TestClassifyDeviceRole:
    def test_switch_from_s_model(self):
        assert classify_device_role("S6850") == DeviceRole.SWITCH

    def test_switch_from_s5130(self):
        assert classify_device_role("S5130-28S-EI") == DeviceRole.SWITCH

    def test_router_from_msr(self):
        assert classify_device_role("MSR 3620") == DeviceRole.ROUTER

    def test_router_from_cr(self):
        assert classify_device_role("CR 16000") == DeviceRole.ROUTER

    def test_router_from_sr(self):
        assert classify_device_role("SR 6600") == DeviceRole.ROUTER

    def test_firewall_raises(self):
        with pytest.raises(UnsupportedProfileError):
            classify_device_role("SecPath F1000")

    def test_firewall_fw_marker(self):
        with pytest.raises(UnsupportedProfileError):
            classify_device_role("FW 1000")

    def test_switch_from_text_marker(self):
        assert classify_device_role("", "H3C S6800 Switch") == DeviceRole.SWITCH

    def test_router_from_text_marker(self):
        assert classify_device_role("", "H3C Router") == DeviceRole.ROUTER

    def test_unknown_role(self):
        assert classify_device_role("UnknownDevice") == DeviceRole.UNKNOWN


class TestDeviceProfile:
    def test_is_supported_v7_switch(self):
        profile = DeviceProfile(
            major_version=ComwareMajorVersion.V7,
            role=DeviceRole.SWITCH,
        )
        assert profile.is_supported is True

    def test_is_supported_v9_router(self):
        profile = DeviceProfile(
            major_version=ComwareMajorVersion.V9,
            role=DeviceRole.ROUTER,
        )
        assert profile.is_supported is True

    def test_not_supported_unknown_role(self):
        profile = DeviceProfile(
            major_version=ComwareMajorVersion.V7,
            role=DeviceRole.UNKNOWN,
        )
        assert profile.is_supported is False

    def test_not_supported_no_version(self):
        profile = DeviceProfile(role=DeviceRole.SWITCH)
        assert profile.is_supported is False

    def test_require_supported_raises(self):
        profile = DeviceProfile(role=DeviceRole.UNKNOWN)
        with pytest.raises(UnsupportedProfileError):
            profile.require_supported()

    def test_frozen(self):
        profile = DeviceProfile(role=DeviceRole.SWITCH)
        with pytest.raises(AttributeError):
            profile.role = DeviceRole.ROUTER


class TestBuildDeviceProfile:
    def test_build_v7_switch(self):
        profile = build_device_profile(
            model="S6850",
            os_version="Comware Software, Version 7.1.070",
        )
        assert profile.major_version == ComwareMajorVersion.V7
        assert profile.role == DeviceRole.SWITCH
        assert profile.model == "S6850"

    def test_build_v9_router(self):
        profile = build_device_profile(
            model="MSR 3620",
            version_output="Comware Software, Version 9.0.021",
        )
        assert profile.major_version == ComwareMajorVersion.V9
        assert profile.role == DeviceRole.ROUTER
