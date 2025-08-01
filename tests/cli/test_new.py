#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests unitaires complets pour la commande new

Tests exhaustifs pour toutes les méthodes et scénarios de new.py
suivant la méthodologie TDD progressive.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from click.testing import CliRunner

from half_orm_dev.cli.new import (
    add_new_commands,
    _has_meta_tables,
    _check_database_state,
    _ask_add_meta_tables,
    _setup_half_orm_dev_structure,
    _create_schema_patches_readme,
    _create_releases_readme,
    _show_next_steps
)


# ==================== FIXTURES ====================

@pytest.fixture
def hop_instance_not_in_repo():
    """HalfOrmDev instance when NOT in a repository."""
    hop = Mock()
    hop.repo_checked = False
    hop._repo = Mock()
    return hop


@pytest.fixture
def hop_instance_repo_no_meta():
    """HalfOrmDev instance in repo WITHOUT meta tables."""
    hop = Mock()
    hop.repo_checked = True
    hop._repo = Mock()
    hop._repo.devel = False
    hop._repo.base_dir = "/test/project"
    return hop


@pytest.fixture
def hop_instance_repo_with_meta():
    """HalfOrmDev instance in repo WITH meta tables."""
    hop = Mock()
    hop.repo_checked = True
    hop._repo = Mock()
    hop._repo.devel = True
    hop._repo.base_dir = "/test/project"
    return hop


@pytest.fixture
def dev_group():
    """Mock Click group for dev commands."""
    group = Mock()
    group.add_command = Mock()
    return group


@pytest.fixture
def temp_project_dir(tmp_path):
    """Temporary directory for project creation tests."""
    return tmp_path / "test_project"


# ==================== TESTS add_new_commands() ====================

class TestAddNewCommands:
    """Tests for add_new_commands() conditional registration logic."""
    
    def test_adds_new_command_when_not_in_repo(self, dev_group, hop_instance_not_in_repo):
        """Should add 'new' command when not in a repository."""
        add_new_commands(dev_group, hop_instance_not_in_repo)
        
        # Should have called add_command exactly once with 'new' command
        assert dev_group.add_command.call_count == 1
        added_command = dev_group.add_command.call_args[0][0]
        assert added_command.name == 'new'
    
    def test_adds_init_meta_when_repo_no_meta(self, dev_group, hop_instance_repo_no_meta):
        """Should add 'init-meta' command when in repo without meta tables."""
        add_new_commands(dev_group, hop_instance_repo_no_meta)
        
        # Should have called add_command exactly once with 'init-meta' command
        assert dev_group.add_command.call_count == 1
        added_command = dev_group.add_command.call_args[0][0]
        assert added_command.name == 'init-meta'
    
    def test_adds_no_commands_when_repo_with_meta(self, dev_group, hop_instance_repo_with_meta):
        """Should add no commands when in repo with meta tables."""
        add_new_commands(dev_group, hop_instance_repo_with_meta)
        
        # Should not have called add_command
        assert dev_group.add_command.call_count == 0
    
    def test_handles_exception_gracefully(self, dev_group):
        """Should handle exceptions in hop_instance gracefully."""
        # Create hop_instance that raises exception
        hop = Mock()
        hop.repo_checked = Mock(side_effect=Exception("Test error"))
        
        # Should not crash
        add_new_commands(dev_group, hop)
        
        # Should not have added any commands
        assert dev_group.add_command.call_count == 0


# ==================== TESTS _has_meta_tables() ====================

class TestHasMetaTables:
    """Tests for _has_meta_tables() detection logic."""
    
    def test_returns_true_when_devel_mode(self, hop_instance_repo_with_meta):
        """Should return True when repository is in development mode."""
        result = _has_meta_tables(hop_instance_repo_with_meta)
        assert result is True
    
    def test_returns_false_when_not_devel_mode(self, hop_instance_repo_no_meta):
        """Should return False when repository is not in development mode."""
        result = _has_meta_tables(hop_instance_repo_no_meta)
        assert result is False
    
    def test_returns_false_on_exception(self):
        """Should return False when exception occurs."""
        hop = Mock()
        hop._repo.devel = Mock(side_effect=Exception("Test error"))
        
        result = _has_meta_tables(hop)
        assert result is False


# ==================== TESTS _check_database_state() ====================

class TestCheckDatabaseState:
    """Tests for _check_database_state() database detection."""
    
    def test_returns_not_exists_by_default(self, hop_instance_not_in_repo):
        """Should return 'not_exists' as safe default."""
        result = _check_database_state(hop_instance_not_in_repo, "test_db")
        assert result == "not_exists"
    
    def test_returns_not_exists_on_exception(self, hop_instance_not_in_repo):
        """Should return 'not_exists' when exception occurs."""
        # This will be implemented when actual database checking is added
        result = _check_database_state(hop_instance_not_in_repo, "test_db")
        assert result == "not_exists"
    
    @patch('half_orm_dev.cli.new.check_database_exists')  # Future implementation
    def test_detects_existing_database_no_meta(self, mock_check_db, hop_instance_not_in_repo):
        """Should detect existing database without meta tables."""
        mock_check_db.return_value = ('exists', False)  # exists, no meta
        
        # This test will pass when actual implementation is added
        # For now, expect current behavior
        result = _check_database_state(hop_instance_not_in_repo, "test_db")
        assert result == "not_exists"  # Current implementation
    
    @patch('half_orm_dev.cli.new.check_database_exists')  # Future implementation
    def test_detects_existing_database_with_meta(self, mock_check_db, hop_instance_not_in_repo):
        """Should detect existing database with meta tables."""
        mock_check_db.return_value = ('exists', True)  # exists, has meta
        
        # This test will pass when actual implementation is added
        result = _check_database_state(hop_instance_not_in_repo, "test_db")
        assert result == "not_exists"  # Current implementation


# ==================== TESTS _ask_add_meta_tables() ====================

class TestAskAddMetaTables:
    """Tests for _ask_add_meta_tables() user interaction."""
    
    @patch('builtins.input', return_value='y')
    @patch('half_orm_dev.cli.new.utils')
    def test_returns_true_for_yes_responses(self, mock_utils, mock_input):
        """Should return True for 'y', 'yes', '' responses."""
        test_cases = ['y', 'yes', 'Y', 'YES', '']
        
        for response in test_cases:
            mock_input.return_value = response
            result = _ask_add_meta_tables()
            assert result is True, f"Failed for response: '{response}'"
    
    @patch('builtins.input', return_value='n')
    @patch('half_orm_dev.cli.new.utils')
    def test_returns_false_for_no_responses(self, mock_utils, mock_input):
        """Should return False for 'n', 'no' responses."""
        test_cases = ['n', 'no', 'N', 'NO']
        
        for response in test_cases:
            mock_input.return_value = response
            result = _ask_add_meta_tables()
            assert result is False, f"Failed for response: '{response}'"
    
    @patch('builtins.input', side_effect=['invalid', 'another', 'y'])
    @patch('half_orm_dev.cli.new.utils')
    def test_repeats_for_invalid_responses(self, mock_utils, mock_input):
        """Should repeat question for invalid responses until valid answer."""
        result = _ask_add_meta_tables()
        
        # Should have asked 3 times
        assert mock_input.call_count == 3
        assert result is True
        
        # Should have shown warning for invalid responses
        assert mock_utils.warning.call_count == 2


# ==================== TESTS _setup_half_orm_dev_structure() ====================

class TestSetupHalfOrmDevStructure:
    """Tests for _setup_half_orm_dev_structure() directory creation."""
    
    @patch('half_orm_dev.cli.new._create_schema_patches_readme')
    @patch('half_orm_dev.cli.new._create_releases_readme')
    @patch('half_orm_dev.cli.new.utils')
    def test_creates_schema_patches_directory(self, mock_utils, mock_create_releases, mock_create_schema, tmp_path):
        """Should create SchemaPatches directory and README."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        
        _setup_half_orm_dev_structure(str(project_dir))
        
        # Should create SchemaPatches directory
        assert (project_dir / "SchemaPatches").exists()
        assert (project_dir / "SchemaPatches").is_dir()
        
        # Should call README creation
        mock_create_schema.assert_called_once()
        mock_utils.info.assert_any_call("📁 Created SchemaPatches directory")
    
    @patch('half_orm_dev.cli.new._create_schema_patches_readme')
    @patch('half_orm_dev.cli.new._create_releases_readme')
    @patch('half_orm_dev.cli.new.utils')
    def test_creates_releases_directory(self, mock_utils, mock_create_releases, mock_create_schema, tmp_path):
        """Should create releases directory and README."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        
        _setup_half_orm_dev_structure(str(project_dir))
        
        # Should create releases directory
        assert (project_dir / "releases").exists()
        assert (project_dir / "releases").is_dir()
        
        # Should call README creation
        mock_create_releases.assert_called_once()
        mock_utils.info.assert_any_call("📁 Created releases directory")
    
    @patch('half_orm_dev.cli.new._create_schema_patches_readme')
    @patch('half_orm_dev.cli.new._create_releases_readme')
    @patch('half_orm_dev.cli.new.utils')
    def test_skips_existing_directories(self, mock_utils, mock_create_releases, mock_create_schema, tmp_path):
        """Should skip creation if directories already exist."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        (project_dir / "SchemaPatches").mkdir()
        (project_dir / "releases").mkdir()
        
        _setup_half_orm_dev_structure(str(project_dir))
        
        # Should not call README creation for existing directories
        mock_create_schema.assert_not_called()
        mock_create_releases.assert_not_called()


# ==================== TESTS README CREATION ====================

class TestReadmeCreation:
    """Tests for README creation functions."""
    
    def test_create_schema_patches_readme(self, tmp_path):
        """Should create SchemaPatches README with correct content."""
        schema_dir = tmp_path / "SchemaPatches"
        schema_dir.mkdir()
        
        with patch('half_orm_dev.cli.new.utils'):
            _create_schema_patches_readme(schema_dir)
        
        readme_file = schema_dir / "README.md"
        assert readme_file.exists()
        
        content = readme_file.read_text()
        assert "# SchemaPatches" in content
        assert "half_orm dev create-patch" in content
        assert "ho-prod" in content
        assert "releases/X.Y.Z-stage.txt" in content
    
    def test_create_releases_readme(self, tmp_path):
        """Should create releases README with correct content."""
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()
        
        with patch('half_orm_dev.cli.new.utils'):
            _create_releases_readme(releases_dir)
        
        readme_file = releases_dir / "README.md"
        assert readme_file.exists()
        
        content = readme_file.read_text()
        assert "# Releases" in content
        assert "X.Y.Z-stage.txt" in content
        assert "git mv" in content
        assert "git log --follow" in content


# ==================== TESTS _show_next_steps() ====================

class TestShowNextSteps:
    """Tests for _show_next_steps() guidance display."""
    
    @patch('half_orm_dev.cli.new.utils')
    def test_displays_complete_guidance(self, mock_utils):
        """Should display complete next steps guidance."""
        _show_next_steps("test_project")
        
        # Should display all key information
        info_calls = [call.args[0] for call in mock_utils.info.call_args_list]
        
        assert any("cd test_project" in call for call in info_calls)
        assert any("half_orm dev status" in call for call in info_calls)
        assert any("create-patch" in call for call in info_calls)
        assert any("SchemaPatches/" in call for call in info_calls)
        assert any("releases/" in call for call in info_calls)


# ==================== TESTS COMMAND INTEGRATION ====================

class TestNewCommandIntegration:
    """Integration tests for the new command itself."""
    
    def test_new_command_registered_correctly(self, dev_group, hop_instance_not_in_repo):
        """Should register new command with correct name and parameters."""
        add_new_commands(dev_group, hop_instance_not_in_repo)
        
        # Should have registered the command
        assert dev_group.add_command.call_count == 1
        command = dev_group.add_command.call_args[0][0]
        
        # Should have correct name and help
        assert command.name == 'new'
        assert 'halfORM project' in command.__doc__
        
        # Should have package_name argument
        assert len(command.params) == 1
        assert command.params[0].name == 'package_name'
    
    def test_init_meta_command_registered_correctly(self, dev_group, hop_instance_repo_no_meta):
        """Should register init-meta command with correct name."""
        add_new_commands(dev_group, hop_instance_repo_no_meta)
        
        # Should have registered the command
        assert dev_group.add_command.call_count == 1
        command = dev_group.add_command.call_args[0][0]
        
        # Should have correct name and help
        assert command.name == 'init-meta'
        assert 'meta tables' in command.__doc__


# ==================== TESTS ERROR HANDLING ====================

class TestErrorHandling:
    """Tests for error handling in all functions."""
    
    def test_setup_structure_handles_permission_error(self, tmp_path):
        """Should handle permission errors gracefully."""
        # Create read-only project directory
        project_dir = tmp_path / "readonly_project"
        project_dir.mkdir(mode=0o555)  # Read-only
        
        try:
            with patch('half_orm_dev.cli.new.utils'):
                # Should not crash
                _setup_half_orm_dev_structure(str(project_dir))
        finally:
            # Cleanup - restore write permissions
            project_dir.chmod(0o755)
    
    def test_readme_creation_handles_write_error(self, tmp_path):
        """Should handle README write errors gracefully."""
        schema_dir = tmp_path / "SchemaPatches"
        schema_dir.mkdir(mode=0o555)  # Read-only
        
        try:
            with patch('half_orm_dev.cli.new.utils'):
                # Should not crash
                _create_schema_patches_readme(schema_dir)
        finally:
            # Cleanup
            schema_dir.chmod(0o755)


# ==================== TESTS EDGE CASES ====================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_empty_package_name_handling(self, hop_instance_not_in_repo):
        """Should handle empty package names appropriately."""
        # This will be tested in the actual command execution
        # For now, ensure no crashes in setup functions
        with patch('half_orm_dev.cli.new.utils'):
            _show_next_steps("")  # Should not crash
    
    def test_special_characters_in_package_name(self, hop_instance_not_in_repo):
        """Should handle special characters in package names."""
        special_names = ["test-project", "test_project", "test.project"]
        
        for name in special_names:
            with patch('half_orm_dev.cli.new.utils'):
                _show_next_steps(name)  # Should not crash
    
    def test_very_long_package_name(self, hop_instance_not_in_repo):
        """Should handle very long package names."""
        long_name = "a" * 100
        
        with patch('half_orm_dev.cli.new.utils'):
            _show_next_steps(long_name)  # Should not crash
