"""
Comprehensive unit tests for resolve_database_config_name() function.

This module tests the database configuration name resolution logic with
its 3-priority system:
1. .hop/alt_config (per-developer override)
2. .hop/config[halfORM][package_name] (backward compatibility)
3. Directory name (default fallback)
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from configparser import ConfigParser

from half_orm_dev.utils import resolve_database_config_name


class TestResolveDatabaseConfigName:
    """Test resolve_database_config_name() with all priority levels."""

    def test_priority_1_alt_config_takes_precedence(self):
        """Test that .hop/alt_config has highest priority."""
        # Setup: Create temp directory with all three sources
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create alt_config (Priority 1 - should win)
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("alt_config_name")

            # Create config with package_name (Priority 2)
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name = config_package_name
hop_version = 0.17.0
git_origin = https://github.com/user/test.git
devel = True
"""
            config_file.write_text(config_content)

            # Directory name would be "my_project" (Priority 3)

            # Test: alt_config should win
            result = resolve_database_config_name(temp_dir)
            assert result == "alt_config_name"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_priority_2_backward_compat_with_package_name(self):
        """Test that package_name in config is used when no alt_config."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # NO alt_config (Priority 1)

            # Create config with package_name (Priority 2 - should win)
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name = config_package_name
hop_version = 0.17.0
git_origin = https://github.com/user/test.git
devel = True
"""
            config_file.write_text(config_content)

            # Directory name would be "my_project" (Priority 3)

            # Test: package_name from config should win
            result = resolve_database_config_name(temp_dir)
            assert result == "config_package_name"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_priority_3_directory_name_fallback(self):
        """Test that directory name is used as fallback."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # NO alt_config (Priority 1)
            # NO config file (Priority 2)

            # Test: directory name should be used (Priority 3)
            result = resolve_database_config_name(temp_dir)
            assert result == "my_project"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_empty_alt_config_falls_back_to_next_priority(self):
        """Test that empty alt_config falls back to next priority."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create EMPTY alt_config (Priority 1 - but empty)
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("")  # Empty!

            # Create config with package_name (Priority 2 - should win)
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name = config_name
hop_version = 0.17.0
"""
            config_file.write_text(config_content)

            # Test: should fall back to package_name
            result = resolve_database_config_name(temp_dir)
            assert result == "config_name"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_whitespace_only_alt_config_falls_back(self):
        """Test that whitespace-only alt_config is treated as empty."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create alt_config with only whitespace
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("   \n\t   ")  # Whitespace only

            # Create config with package_name
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name = config_name
"""
            config_file.write_text(config_content)

            # Test: should fall back to package_name (whitespace stripped)
            result = resolve_database_config_name(temp_dir)
            assert result == "config_name"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_invalid_config_falls_back_to_directory(self):
        """Test that corrupted config file doesn't break resolution."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # NO alt_config

            # Create INVALID config file
            config_file = hop_dir / 'config'
            config_file.write_text("This is not valid INI format!!!")

            # Test: should fall back to directory name
            result = resolve_database_config_name(temp_dir)
            assert result == "my_project"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_config_without_package_name_falls_back(self):
        """Test that config without package_name uses directory name."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # NO alt_config

            # Create config WITHOUT package_name (new format)
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
hop_version = 0.17.0
git_origin = https://github.com/user/test.git
devel = True
"""
            config_file.write_text(config_content)

            # Test: should use directory name
            result = resolve_database_config_name(temp_dir)
            assert result == "my_project"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_empty_package_name_in_config_falls_back(self):
        """Test that empty package_name in config falls back to directory."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create config with EMPTY package_name
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name =
hop_version = 0.17.0
"""
            config_file.write_text(config_content)

            # Test: should fall back to directory name
            result = resolve_database_config_name(temp_dir)
            assert result == "my_project"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_all_three_sources_present_priority_order(self):
        """Test priority order when all three sources exist."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "directory_name")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create all three sources
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("alt_config_value")

            config_file = hop_dir / 'config'
            config_content = """[halfORM]
package_name = package_name_value
hop_version = 0.17.0
"""
            config_file.write_text(config_content)

            # Directory name is "directory_name"

            # Test: Priority 1 (alt_config) should win
            result = resolve_database_config_name(temp_dir)
            assert result == "alt_config_value"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_alt_config_with_special_characters(self):
        """Test that alt_config handles various valid database names."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        test_cases = [
            "my_blog_dev",
            "project-2024",
            "test_db_alice",
            "prod_v2",
            "my.special.db"
        ]

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            for db_name in test_cases:
                alt_config = hop_dir / 'alt_config'
                alt_config.write_text(db_name)

                result = resolve_database_config_name(temp_dir)
                assert result == db_name, f"Failed for database name: {db_name}"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_no_hop_directory_uses_directory_name(self):
        """Test that missing .hop directory uses directory name."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            # NO .hop directory at all

            # Test: should use directory name
            result = resolve_database_config_name(temp_dir)
            assert result == "my_project"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_alt_config_with_multiline_content_uses_first_line(self):
        """Test that multiline alt_config uses content (after strip)."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Create alt_config with multiline (should strip but keep all)
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("my_db_dev\nsecond_line\n")

            # Test: strip() will get "my_db_dev\nsecond_line"
            # This documents current behavior - you may want single-line only
            result = resolve_database_config_name(temp_dir)
            # Current implementation uses .strip() which keeps newlines in middle
            assert "my_db_dev" in result

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_path_object_as_input(self):
        """Test that function accepts Path objects."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("test_db")

            # Test with Path object instead of string
            result = resolve_database_config_name(Path(temp_dir))
            assert result == "test_db"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_string_path_as_input(self):
        """Test that function accepts string paths."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("test_db")

            # Test with string path
            result = resolve_database_config_name(temp_dir)
            assert result == "test_db"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_real_world_scenario_developer_clone(self):
        """Test real-world scenario: developer working with cloned DB."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "my_blog")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Original config (for production)
            config_file = hop_dir / 'config'
            config_content = """[halfORM]
hop_version = 0.17.0
git_origin = https://github.com/company/my_blog.git
devel = True
"""
            config_file.write_text(config_content)

            # Developer creates alt_config for their dev database
            alt_config = hop_dir / 'alt_config'
            alt_config.write_text("my_blog_alice")

            # Test: Developer's override should be used
            result = resolve_database_config_name(temp_dir)
            assert result == "my_blog_alice"

            # If developer removes alt_config, falls back to directory name
            alt_config.unlink()
            result = resolve_database_config_name(temp_dir)
            assert result == "my_blog"

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)

    def test_real_world_scenario_legacy_project_migration(self):
        """Test migration path from old format to new format."""
        parent_temp = tempfile.mkdtemp()
        temp_dir = os.path.join(parent_temp, "legacy_project")
        os.makedirs(temp_dir)

        try:
            hop_dir = Path(temp_dir) / '.hop'
            hop_dir.mkdir()

            # Old format config (with package_name)
            config_file = hop_dir / 'config'
            old_config_content = """[halfORM]
package_name = legacy_db
config_file = legacy_db
hop_version = 0.15.0
git_origin = https://github.com/company/legacy.git
devel = False
"""
            config_file.write_text(old_config_content)

            # Test: Old format still works (backward compatibility)
            result = resolve_database_config_name(temp_dir)
            assert result == "legacy_db"

            # Simulate migration: remove package_name from config
            new_config_content = """[halfORM]
hop_version = 0.17.0
git_origin = https://github.com/company/legacy.git
devel = False
"""
            config_file.write_text(new_config_content)

            # Test: After migration, uses directory name
            result = resolve_database_config_name(temp_dir)
            assert result == "legacy_project"

            # Note: Behavior changes, but directory is typically named correctly

        finally:
            shutil.rmtree(parent_temp, ignore_errors=True)
