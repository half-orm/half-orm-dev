"""
Integration tests for 'half_orm dev init-project' CLI command (development mode).

Tests end-to-end project creation via subprocess with real database.
Verifies Git structure, development directories, Python package, and configuration.
"""

import pytest
import subprocess
import configparser
from pathlib import Path


@pytest.mark.integration
class TestInitProjectGitStructure:
    """Test Git repository initialization."""

    def test_init_project_creates_git_repository(self, devel_project):
        """Test that init-project creates Git repository with ho-prod branch."""
        project_dir, db_name, _ = devel_project

        # Verify .git directory exists
        git_dir = project_dir / ".git"
        assert git_dir.exists(), "Git repository not initialized"
        assert git_dir.is_dir(), ".git should be a directory"

        # Verify ho-prod branch is active
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ho-prod", "Should be on ho-prod branch"

        # Verify initial commit exists
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(project_dir),
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0, "Should have initial commit"


@pytest.mark.integration
class TestInitProjectDevelopmentDirectories:
    """Test development directory structure creation."""

    def test_init_project_creates_development_directories(self, devel_project):
        """Test that all development directories are created with README files."""
        project_dir, db_name, _ = devel_project

        # Verify Patches/ directory
        patches_dir = project_dir / "Patches"
        assert patches_dir.exists(), "Patches/ directory not created"
        assert patches_dir.is_dir(), "Patches/ should be a directory"
        assert (patches_dir / "README.md").exists(), "Patches/README.md missing"

        # Verify releases/ directory
        releases_dir = project_dir / ".hop" / "releases"
        assert releases_dir.exists(), "releases/ directory not created"
        assert releases_dir.is_dir(), "releases/ should be a directory"
        assert (releases_dir / "README.md").exists(), "releases/README.md missing"

        # Verify model/ directory
        model_dir = project_dir / "model"
        assert model_dir.exists(), "model/ directory not created"
        assert model_dir.is_dir(), "model/ should be a directory"

        # Verify model/schema-0.0.0.sql sql dump
        schema_dump = model_dir / "schema-0.0.0.sql"
        assert schema_dump.exists(), "model/schema-0.0.0.sql dump not created"
        assert schema_dump.is_file(), "model/schema.sql should be a file"

        # Verify model/metadata-0.0.0.sql sql dump
        schema_dump = model_dir / "metadata-0.0.0.sql"
        assert schema_dump.exists(), "model/metadata-0.0.0.sql dump not created"
        assert schema_dump.is_file(), "model/metadata.sql should be a file"

        # Verify model/schema.sql symlink
        schema_link = model_dir / "schema.sql"
        assert schema_link.exists(), "model/schema.sql symlink not created"
        assert schema_link.is_symlink(), "model/schema.sql should be a link"
        assert str(schema_link.readlink()) == "schema-0.0.0.sql"

        # Verify model/ directory
        schema_link = model_dir / "schema.sql"
        assert schema_link.exists(), "model/schema.sql link not created"
        assert schema_link.is_symlink(), "model/schema.sql should be a link"

        # Verify backups/ directory
        backups_dir = project_dir / "backups"
        assert backups_dir.exists(), "backups/ directory not created"
        assert backups_dir.is_dir(), "backups/ should be a directory"


@pytest.mark.integration
class TestInitProjectPythonPackage:
    """Test Python package generation."""

    def test_init_project_generates_python_package(self, devel_project):
        """Test that Python package is generated from database schema."""
        project_dir, db_name, _ = devel_project

        # Verify Python package directory exists (named after database)
        package_dir = project_dir / db_name
        assert package_dir.exists(), f"Python package {db_name}/ not created"
        assert package_dir.is_dir(), "Package should be a directory"

        # Verify __init__.py exists (makes it a Python package)
        init_file = package_dir / "__init__.py"
        assert init_file.exists(), "__init__.py not created in package"


@pytest.mark.integration
class TestInitProjectConfiguration:
    """Test project configuration file creation."""

    def test_init_project_creates_hop_config(self, devel_project):
        """Test that .hop/config is created with correct content."""
        project_dir, db_name, git_origin = devel_project

        # Verify .hop/config exists
        config_file = project_dir / ".hop" / "config"
        assert config_file.exists(), ".hop/config not created"

        # Parse configuration
        config = configparser.ConfigParser()
        config.read(str(config_file))
        # Verify [halfORM] section exists
        assert config.has_section('halfORM'), "[halfORM] section missing"

        # Verify package_name
        assert config.has_option('halfORM', 'package_name'), "package_name missing"
        assert config.get('halfORM', 'package_name') == db_name

        # Verify git_origin
        assert config.has_option('halfORM', 'git_origin'), "git_origin missing"
        assert config.get('halfORM', 'git_origin') == f"file://{git_origin}"


@pytest.mark.integration
class TestInitProjectDevelopmentMode:
    """Test development mode detection."""

    def test_init_project_development_mode_detected(self, devel_project):
        """Test that Repo correctly detects development mode (repo.devel = True)."""
        project_dir, db_name, _ = devel_project

        # Import Repo in project context
        import os
        from half_orm_dev.repo import Repo

        # Change to project directory (Repo uses cwd)
        original_cwd = os.getcwd()
        try:
            os.chdir(str(project_dir))

            # Create Repo instance
            repo = Repo()

            # Verify development mode is detected
            assert repo.devel is True, "Development mode not detected (repo.devel should be True)"

            # Verify database has metadata (required for devel mode)
            # This is already verified by initialized_database fixture,
            # but we can double-check via Repo
            assert repo.name == db_name, f"Repo database name mismatch: {repo.name} != {db_name}"

        finally:
            os.chdir(original_cwd)
