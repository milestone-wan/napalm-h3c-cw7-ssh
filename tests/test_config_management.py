#
# Copyright 2022 milestone. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#

"""Unit tests for configuration management methods."""

import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from napalm.base.exceptions import ReplaceConfigException, MergeConfigException

from napalm_h3c_comware.comware import ComwareDriver, COMWARE_CONFIG_ERROR_PATTERNS
from napalm_h3c_comware.exceptions import ConfigManagementError
from napalm_h3c_comware.profiles import DeviceProfile, ComwareMajorVersion, DeviceRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RUNNING_CONFIG = """\
#
version 7.1.070, Release 2432P02
#
sysname Switch
#
interface GigabitEthernet1/0/1
 port link-mode bridge
 port access vlan 10
#
interface GigabitEthernet1/0/2
 port link-mode bridge
 port access vlan 20
#
return
"""

ARCHIVE_ENABLED_OUTPUT = """\
Archive configuration is enabled.
Archive location: flash:/archive
Maximum number of archive files: 5
"""

ARCHIVE_NOT_ENABLED_OUTPUT = """\
Archive configuration is not enabled.
"""


@pytest.fixture
def driver():
    """Create a ComwareDriver with mocked device connection."""
    d = ComwareDriver("localhost", "admin", "admin")
    d.device = MagicMock()
    d.device.check_config_mode.return_value = False
    d.device.send_config_set.return_value = ""
    d.device.save_config.return_value = "Configuration saved successfully."
    d.device.send_command.return_value = ""
    d.profile = DeviceProfile(
        major_version=ComwareMajorVersion.V7,
        role=DeviceRole.SWITCH,
    )
    # Mock send_command to return running config by default
    d.send_command = MagicMock(return_value=SAMPLE_RUNNING_CONFIG)
    return d


@pytest.fixture
def driver_with_archive(driver):
    """Create a driver with archive configuration enabled on the device."""
    # Override send_command to return archive-enabled output for specific commands
    original_send_command = driver.send_command

    def mock_send_command(cmd, *args, **kwargs):
        if "display archive configuration" in cmd:
            return ARCHIVE_ENABLED_OUTPUT
        return original_send_command(cmd, *args, **kwargs)

    driver.send_command = mock_send_command
    return driver


# ---------------------------------------------------------------------------
# _read_candidate_config
# ---------------------------------------------------------------------------

class TestReadCandidateConfig:

    def test_from_string(self, driver):
        result = driver._read_candidate_config(config="interface GE1/0/1\n ip address 10.0.0.1/24")
        assert result == "interface GE1/0/1\n ip address 10.0.0.1/24"

    def test_from_file(self, driver):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("interface GE1/0/1\n ip address 10.0.0.1/24")
            f.flush()
            result = driver._read_candidate_config(filename=f.name)
        os.unlink(f.name)
        assert result == "interface GE1/0/1\n ip address 10.0.0.1/24"

    def test_file_takes_precedence(self, driver):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("from file")
            f.flush()
            result = driver._read_candidate_config(filename=f.name, config="from string")
        os.unlink(f.name)
        assert result == "from file"

    def test_no_args_raises(self, driver):
        with pytest.raises(ValueError, match="Either filename or config"):
            driver._read_candidate_config()

    def test_file_not_found(self, driver):
        with pytest.raises(IOError):
            driver._read_candidate_config(filename="/nonexistent/path/config.txt")


# ---------------------------------------------------------------------------
# _check_config_errors
# ---------------------------------------------------------------------------

class TestCheckConfigErrors:

    def test_no_errors(self, driver):
        output = "interface GE1/0/1\n ip address 10.0.0.1/24"
        assert driver._check_config_errors(output) == []

    def test_unrecognized_command(self, driver):
        output = "interface GE1/0/1\n% Unrecognized command found at '^' position."
        errors = driver._check_config_errors(output)
        assert len(errors) == 1
        assert "Unrecognized command" in errors[0]

    def test_ambiguous_command(self, driver):
        output = "% Ambiguous command found at '^' position."
        errors = driver._check_config_errors(output)
        assert len(errors) == 1
        assert "Ambiguous command" in errors[0]

    def test_incomplete_command(self, driver):
        output = "% Incomplete command found at '^' position."
        errors = driver._check_config_errors(output)
        assert len(errors) == 1
        assert "Incomplete command" in errors[0]

    def test_multiple_errors(self, driver):
        output = "% Unrecognized command\n% Incomplete command"
        errors = driver._check_config_errors(output)
        assert len(errors) == 2

    def test_normal_output_no_false_positive(self, driver):
        output = "interface GigabitEthernet1/0/1\n port link-mode bridge"
        assert driver._check_config_errors(output) == []


# ---------------------------------------------------------------------------
# _check_archive_feature
# ---------------------------------------------------------------------------

class TestCheckArchiveFeature:

    def test_archive_enabled(self, driver):
        driver.send_command = MagicMock(return_value=ARCHIVE_ENABLED_OUTPUT)
        assert driver._check_archive_feature() is True

    def test_archive_not_enabled(self, driver):
        driver.send_command = MagicMock(return_value=ARCHIVE_NOT_ENABLED_OUTPUT)
        assert driver._check_archive_feature() is False

    def test_archive_check_exception(self, driver):
        driver.send_command = MagicMock(side_effect=Exception("Connection lost"))
        assert driver._check_archive_feature() is False


# ---------------------------------------------------------------------------
# _gen_full_path
# ---------------------------------------------------------------------------

class TestGenFullPath:

    def test_default_filesystem(self, driver):
        assert driver._gen_full_path("candidate_config.txt") == "flash:/candidate_config.txt"

    def test_custom_filesystem(self):
        d = ComwareDriver("localhost", "admin", "admin",
                          optional_args={"dest_file_system": "cfcard:"})
        assert d._gen_full_path("rollback_config.txt") == "cfcard:/rollback_config.txt"


# ---------------------------------------------------------------------------
# load_merge_candidate
# ---------------------------------------------------------------------------

class TestLoadMergeCandidate:

    def test_from_string(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3\n port access vlan 30")
        assert driver._loaded is True
        assert driver._config_replace is False
        assert "GE1/0/3" in driver._candidate_config

    def test_from_file(self, driver):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("interface GE1/0/3\n port access vlan 30")
            f.flush()
            driver.load_merge_candidate(filename=f.name)
        os.unlink(f.name)
        assert driver._loaded is True
        assert "GE1/0/3" in driver._candidate_config

    def test_no_args_raises(self, driver):
        with pytest.raises(MergeConfigException):
            driver.load_merge_candidate()

    def test_file_not_found_raises(self, driver):
        with pytest.raises(MergeConfigException):
            driver.load_merge_candidate(filename="/nonexistent/path/config.txt")


# ---------------------------------------------------------------------------
# load_replace_candidate
# ---------------------------------------------------------------------------

class TestLoadReplaceCandidate:

    def test_from_string(self, driver):
        driver.load_replace_candidate(config="sysname NewSwitch")
        assert driver._loaded is True
        assert driver._config_replace is True
        assert "NewSwitch" in driver._candidate_config

    def test_no_args_raises(self, driver):
        with pytest.raises(ReplaceConfigException):
            driver.load_replace_candidate()


# ---------------------------------------------------------------------------
# compare_config
# ---------------------------------------------------------------------------

class TestCompareConfig:

    def test_no_candidate_returns_empty(self, driver):
        assert driver.compare_config() == ""

    def test_merge_diff_shows_new_lines(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3\n port access vlan 30")
        diff = driver.compare_config()
        assert "+" in diff
        assert "GE1/0/3" in diff

    def test_replace_diff_shows_full_diff(self, driver):
        driver.load_replace_candidate(config="sysname NewSwitch\nreturn")
        diff = driver.compare_config()
        # Replace mode uses unified diff — should show changes
        assert diff != ""

    def test_identical_config_returns_empty(self, driver):
        driver.load_merge_candidate(config=SAMPLE_RUNNING_CONFIG)
        diff = driver.compare_config()
        assert diff == ""


# ---------------------------------------------------------------------------
# commit_config — merge mode
# ---------------------------------------------------------------------------

class TestCommitConfigMerge:

    def test_merge_commit_success(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3\n port access vlan 30")
        driver.commit_config()
        driver.device.send_config_set.assert_called_once()
        driver.device.save_config.assert_called_once()
        assert driver._loaded is False
        assert driver._candidate_config == ""

    def test_no_candidate_raises(self, driver):
        with pytest.raises(ConfigManagementError, match="No candidate configuration loaded"):
            driver.commit_config()

    def test_revert_in_not_supported(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3")
        with pytest.raises(NotImplementedError, match="revert_in"):
            driver.commit_config(revert_in=60)

    def test_commit_with_errors_triggers_rollback(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3")
        driver.device.send_config_set.return_value = "% Unrecognized command found"
        # rollback needs send_config_set too
        driver._pre_commit_config = SAMPLE_RUNNING_CONFIG
        with pytest.raises(MergeConfigException, match="Configuration merge failed"):
            driver.commit_config()

    def test_empty_candidate_no_op(self, driver):
        driver.load_merge_candidate(config="   \n\n  ")
        driver.commit_config()
        driver.device.send_config_set.assert_not_called()
        assert driver._loaded is False

    def test_save_failure_raises(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3\n port access vlan 30")
        driver.device.save_config.side_effect = Exception("Save failed")
        with pytest.raises(ConfigManagementError, match="save failed"):
            driver.commit_config()

    def test_pre_commit_snapshot_saved(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3\n port access vlan 30")
        driver.commit_config()
        # Verify the snapshot was taken by checking send_command was called
        driver.send_command.assert_called()


# ---------------------------------------------------------------------------
# commit_config — replace mode
# ---------------------------------------------------------------------------

class TestCommitConfigReplace:

    def test_replace_without_archive_raises(self, driver):
        """Replace mode requires archive configuration to be enabled."""
        driver.send_command = MagicMock(return_value=ARCHIVE_NOT_ENABLED_OUTPUT)
        driver.load_replace_candidate(config="sysname NewSwitch")
        with pytest.raises(ReplaceConfigException, match="archive configuration"):
            driver.commit_config()

    @patch("napalm_h3c_comware.comware.HPComwareFileTransfer")
    def test_replace_with_archive_success(self, mock_transfer_cls, driver_with_archive):
        """Replace mode succeeds when archive is enabled and file transfer works."""
        mock_transfer = MagicMock()
        mock_transfer.__enter__ = MagicMock(return_value=mock_transfer)
        mock_transfer.__exit__ = MagicMock(return_value=False)
        mock_transfer.verify_space_available.return_value = True
        mock_transfer.verify_file.return_value = True
        mock_transfer_cls.return_value = mock_transfer

        driver_with_archive.device.send_command.return_value = "Configuration replaced successfully"
        driver_with_archive.load_replace_candidate(config="sysname NewSwitch\nreturn")
        driver_with_archive.commit_config()

        mock_transfer_cls.assert_called_once()
        mock_transfer.transfer_file.assert_called_once()
        driver_with_archive.device.save_config.assert_called_once()
        assert driver_with_archive._loaded is False

    @patch("napalm_h3c_comware.comware.HPComwareFileTransfer")
    def test_replace_transfer_failure_raises(self, mock_transfer_cls, driver_with_archive):
        """Replace mode raises when file transfer fails."""
        mock_transfer = MagicMock()
        mock_transfer.__enter__ = MagicMock(return_value=mock_transfer)
        mock_transfer.__exit__ = MagicMock(return_value=False)
        mock_transfer.verify_space_available.return_value = True
        mock_transfer.transfer_file.side_effect = Exception("SCP failed")
        mock_transfer_cls.return_value = mock_transfer

        driver_with_archive.load_replace_candidate(config="sysname NewSwitch")
        with pytest.raises(ReplaceConfigException, match="Failed to transfer"):
            driver_with_archive.commit_config()

    @patch("napalm_h3c_comware.comware.HPComwareFileTransfer")
    def test_replace_command_error_raises(self, mock_transfer_cls, driver_with_archive):
        """Replace mode raises when configuration replace command fails."""
        mock_transfer = MagicMock()
        mock_transfer.__enter__ = MagicMock(return_value=mock_transfer)
        mock_transfer.__exit__ = MagicMock(return_value=False)
        mock_transfer.verify_space_available.return_value = True
        mock_transfer.verify_file.return_value = True
        mock_transfer_cls.return_value = mock_transfer

        driver_with_archive.device.send_command.return_value = "Error: File not found"
        driver_with_archive.load_replace_candidate(config="sysname NewSwitch")
        with pytest.raises(ReplaceConfigException, match="Configuration replace failed"):
            driver_with_archive.commit_config()


# ---------------------------------------------------------------------------
# discard_config
# ---------------------------------------------------------------------------

class TestDiscardConfig:

    def test_discard_clears_state(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3")
        assert driver._loaded is True
        driver.discard_config()
        assert driver._loaded is False
        assert driver._candidate_config == ""
        assert driver._config_replace is False

    def test_compare_after_discard_returns_empty(self, driver):
        driver.load_merge_candidate(config="interface GE1/0/3")
        driver.discard_config()
        assert driver.compare_config() == ""


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

class TestRollback:

    def test_rollback_with_snapshot_no_archive(self, driver):
        """Rollback falls back to snapshot replay when archive is not enabled."""
        driver.send_command = MagicMock(return_value=ARCHIVE_NOT_ENABLED_OUTPUT)
        driver._pre_commit_config = SAMPLE_RUNNING_CONFIG
        driver.rollback()
        driver.device.send_config_set.assert_called_once()
        driver.device.save_config.assert_called_once()
        assert driver._pre_commit_config == ""

    @patch("napalm_h3c_comware.comware.HPComwareFileTransfer")
    def test_rollback_with_archive(self, mock_transfer_cls, driver_with_archive):
        """Rollback uses configuration replace file when archive is enabled."""
        mock_transfer = MagicMock()
        mock_transfer.__enter__ = MagicMock(return_value=mock_transfer)
        mock_transfer.__exit__ = MagicMock(return_value=False)
        mock_transfer.verify_space_available.return_value = True
        mock_transfer.verify_file.return_value = True
        mock_transfer_cls.return_value = mock_transfer

        driver_with_archive.device.send_command.return_value = "Configuration replaced successfully"
        driver_with_archive._pre_commit_config = SAMPLE_RUNNING_CONFIG
        driver_with_archive.rollback()

        mock_transfer_cls.assert_called_once()
        mock_transfer.transfer_file.assert_called_once()
        driver_with_archive.device.save_config.assert_called()
        assert driver_with_archive._pre_commit_config == ""

    @patch("napalm_h3c_comware.comware.HPComwareFileTransfer")
    def test_rollback_archive_falls_back_to_snapshot(self, mock_transfer_cls, driver_with_archive):
        """Rollback falls back to snapshot when archive transfer fails."""
        mock_transfer = MagicMock()
        mock_transfer.__enter__ = MagicMock(return_value=mock_transfer)
        mock_transfer.__exit__ = MagicMock(return_value=False)
        mock_transfer.verify_space_available.return_value = True
        mock_transfer.transfer_file.side_effect = Exception("SCP failed")
        mock_transfer_cls.return_value = mock_transfer

        driver_with_archive._pre_commit_config = SAMPLE_RUNNING_CONFIG
        driver_with_archive.rollback()

        # Should fall back to snapshot-based rollback
        driver_with_archive.device.send_config_set.assert_called_once()
        driver_with_archive.device.save_config.assert_called()
        assert driver_with_archive._pre_commit_config == ""

    def test_no_snapshot_raises(self, driver):
        with pytest.raises(ConfigManagementError, match="No pre-commit configuration snapshot"):
            driver.rollback()

    def test_rollback_failure_raises(self, driver):
        driver.send_command = MagicMock(return_value=ARCHIVE_NOT_ENABLED_OUTPUT)
        driver._pre_commit_config = SAMPLE_RUNNING_CONFIG
        driver.device.send_config_set.side_effect = Exception("Connection lost")
        with pytest.raises(ConfigManagementError, match="Rollback failed"):
            driver.rollback()


# ---------------------------------------------------------------------------
# confirm_commit / has_pending_commit
# ---------------------------------------------------------------------------

class TestConfirmCommit:

    def test_confirm_commit_not_supported(self, driver):
        with pytest.raises(NotImplementedError):
            driver.confirm_commit()

    def test_has_pending_commit_returns_false(self, driver):
        assert driver.has_pending_commit() is False


# ---------------------------------------------------------------------------
# HPComwareFileTransfer
# ---------------------------------------------------------------------------

class TestHPComwareFileTransfer:

    def _make_transfer(self, mock_ssh, dest_file="candidate_config.txt"):
        """Helper to create HPComwareFileTransfer with a real temp source file."""
        from napalm_h3c_comware.comware import HPComwareFileTransfer
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test config content")
            tmp = f.name
        transfer = HPComwareFileTransfer(
            ssh_conn=mock_ssh,
            source_file=tmp,
            dest_file=dest_file,
            file_system="flash:",
            hash_supported=False,
        )
        os.unlink(tmp)
        return transfer

    def test_check_file_exists_true(self):
        mock_ssh = MagicMock()
        mock_ssh.send_command.return_value = "  1234  Jan 01 00:00:00  candidate_config.txt"
        transfer = self._make_transfer(mock_ssh)
        assert transfer.check_file_exists() is True

    def test_check_file_exists_false(self):
        mock_ssh = MagicMock()
        mock_ssh.send_command.return_value = "Error: File not found"
        transfer = self._make_transfer(mock_ssh, dest_file="nonexistent.txt")
        assert transfer.check_file_exists() is False

    def test_remote_md5(self):
        mock_ssh = MagicMock()
        mock_ssh.send_command.return_value = "d41d8cd98f00b204e9800998ecf8427e  flash:/test.txt"
        transfer = self._make_transfer(mock_ssh, dest_file="test.txt")
        assert transfer.remote_md5() == "d41d8cd98f00b204e9800998ecf8427e"

    def test_enable_scp(self):
        mock_ssh = MagicMock()
        transfer = self._make_transfer(mock_ssh)
        transfer.enable_scp()
        mock_ssh.send_config_set.assert_called_with(
            ["scp server enable"],
            enter_config_mode=True,
            exit_config_mode=True,
        )

    def test_disable_scp(self):
        mock_ssh = MagicMock()
        transfer = self._make_transfer(mock_ssh)
        transfer.disable_scp()
        mock_ssh.send_config_set.assert_called_with(
            ["undo scp server enable"],
            enter_config_mode=True,
            exit_config_mode=True,
        )


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------

class TestGetConfig:

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        original = driver.send_command

        def mock_send_command(cmd, *args, **kwargs):
            if "current-configuration" in cmd:
                return SAMPLE_RUNNING_CONFIG
            if "saved-configuration" in cmd:
                return "sysname SavedSwitch\nreturn"
            return original(cmd, *args, **kwargs)

        driver.send_command = mock_send_command
        self.driver = driver

    def test_returns_running_and_startup(self):
        result = self.driver.get_config()
        assert "running" in result
        assert "startup" in result
        assert "candidate" in result
        assert result["candidate"] == ""
        assert "Switch" in result["running"]

    def test_retrieve_running_only(self):
        result = self.driver.get_config(retrieve="running")
        assert result["running"] != ""
        assert result["startup"] == ""

    def test_retrieve_startup_only(self):
        result = self.driver.get_config(retrieve="startup")
        assert result["startup"] != ""
        assert result["running"] == ""

    def test_format_parameter_accepted(self):
        result = self.driver.get_config(format="text")
        assert "running" in result

    def test_full_parameter_accepted_noop(self):
        result = self.driver.get_config(full=True)
        assert "running" in result
        assert "Switch" in result["running"]

    def test_sanitized_removes_passwords(self):
        config_with_secrets = """\
#
sysname Switch
#
local-user admin password simple mypassword123
#
snmp-agent community read public123
#
return
"""
        self.driver.send_command = MagicMock(return_value=config_with_secrets)
        result = self.driver.get_config(sanitized=True)
        assert "mypassword123" not in result["running"]
        assert "public123" not in result["running"]
        assert "<removed>" in result["running"]

    def test_sanitized_preserves_non_secret_lines(self):
        config_with_secrets = """\
#
sysname Switch
#
local-user admin password simple mypassword123
#
interface GigabitEthernet1/0/1
 port access vlan 10
#
return
"""
        self.driver.send_command = MagicMock(return_value=config_with_secrets)
        result = self.driver.get_config(sanitized=True)
        assert "sysname Switch" in result["running"]
        assert "GigabitEthernet1/0/1" in result["running"]
        assert "mypassword123" not in result["running"]

    def test_return_type_is_dict(self):
        result = self.driver.get_config()
        assert isinstance(result, dict)
        assert set(result.keys()) == {"running", "startup", "candidate"}
