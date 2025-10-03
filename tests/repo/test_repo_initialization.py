"""
Tests pour l'initialisation de la classe Repo.

Module de test focalisé uniquement sur TestRepoInitialization :
- Tests d'initialisation et validation repository
- Tests des propriétés checked, devel, production
- Tests de __check et __set_base_dir
- Tests de configuration et état du repository
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from configparser import ConfigParser

from half_orm_dev.repo import Repo, Config


class TestRepoInitialization:
    """Test Repo initialization and repository validation."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @pytest.fixture
    def temp_hop_repo(self):
        """Create temporary directory with .hop/config file."""
        from half_orm_dev.utils import hop_version

        temp_dir = tempfile.mkdtemp()

        try:
            # Create .hop directory
            hop_dir = Path(temp_dir) / ".hop"
            hop_dir.mkdir()

            # Create config file with current hop version (no mocking)
            current_hop_version = hop_version()
            config_file = hop_dir / "config"
            config_content = f"""[halfORM]
package_name = test_db
hop_version = {current_hop_version}
git_origin = https://github.com/user/test.git
devel = True
"""
            config_file.write_text(config_content)

            yield temp_dir

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def temp_non_hop_repo(self):
        """Create temporary directory without .hop/config (not a hop repo)."""
        temp_dir = tempfile.mkdtemp()

        try:
            yield temp_dir
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def temp_production_repo(self):
        """Create temporary directory with production config."""
        from half_orm_dev.utils import hop_version

        temp_dir = tempfile.mkdtemp()

        try:
            # Create .hop directory
            hop_dir = Path(temp_dir) / ".hop"
            hop_dir.mkdir()

            # Create production config file with current hop version
            current_hop_version = hop_version()
            config_file = hop_dir / "config"
            config_content = f"""[halfORM]
package_name = prod_db
hop_version = {current_hop_version}
git_origin = https://github.com/company/prod.git
devel = True
"""
            config_file.write_text(config_content)

            yield temp_dir

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_initialization_in_hop_repo(self, temp_hop_repo):
        """Test Repo initialization in directory with .hop/config."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()

                # Should be checked (valid hop repo)
                assert repo.checked is True
                assert repo.base_dir == temp_hop_repo
                assert repo.name == "test_db"
                assert repo.devel is True

    def test_initialization_outside_hop_repo(self, temp_non_hop_repo):
        """Test Repo initialization outside hop repository."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_non_hop_repo

            repo = Repo()

            # Should not be checked (no .hop/config found)
            assert repo.checked is False
            assert repo.base_dir is None
            assert repo.name is None

    def test_checked_property(self, temp_hop_repo, temp_non_hop_repo):
        """Test checked property returns correct repository status."""
        # Test valid hop repo
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                assert repo.checked is True

        Repo.clear_instances()

        # Test non-hop repo
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_non_hop_repo

            repo = Repo()
            assert repo.checked is False

    def test_production_property(self, temp_hop_repo):
        """Test production property delegates to database."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Test production = True
                mock_database_instance = Mock()
                mock_database_instance.production = True
                mock_db.return_value = mock_database_instance

                repo = Repo()
                assert repo.production is True

        Repo.clear_instances()

        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Test production = False
                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                assert repo.production is False

    def test_model_property_delegates_to_database(self, temp_hop_repo):
        """Test model property delegates to database.model."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_model = Mock()
                mock_database_instance = Mock()
                mock_database_instance.model = mock_model
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                assert repo.model is mock_model

    def test_devel_property_from_config(self, temp_hop_repo):
        """Test devel property reads from config."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                # Config has devel = True
                assert repo.devel is True

    def test_name_property_from_config(self, temp_hop_repo):
        """Test name property reads from config."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                # Config has package_name = test_db
                assert repo.name == "test_db"

    def test_base_dir_property(self, temp_hop_repo):
        """Test base_dir property returns repository base directory."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                assert repo.base_dir == temp_hop_repo

    def test_git_origin_property_getter(self, temp_hop_repo):
        """Test git_origin property getter from config."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                # Config has git_origin = https://github.com/user/test.git
                assert repo.git_origin == "https://github.com/user/test.git"

    def test_git_origin_property_setter(self, temp_hop_repo):
        """Test git_origin property setter updates config."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()

                # Set new origin
                new_origin = "https://github.com/user/new-repo.git"
                repo.git_origin = new_origin

                # Should be updated
                assert repo.git_origin == new_origin

    def test_new_property_false_for_existing_repo(self, temp_hop_repo):
        """Test new property is False for existing repository."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()
                # Existing repo should have new = False
                assert repo.new is False

    def test_database_initialization_in_devel_mode(self, temp_hop_repo):
        """Test Database initialization when in development mode."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()

                # Should create Database, HGit, and Changelog instances
                mock_db.assert_called_once_with(repo)
                mock_hgit.assert_called_once_with(repo)

    def test_state_property_includes_version_info(self, temp_hop_repo):
        """Test state property includes version information."""
        import half_orm
        from half_orm_dev.utils import hop_version

        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit, \
                 patch('half_orm.utils.Color.bold') as mock_color_bold, \
                 patch('half_orm.utils.Color.red') as mock_color_red, \
                 patch('half_orm.utils.Color.green') as mock_color_green:

                # Use real versions - no mocking
                real_ho_version = half_orm.__version__
                real_hop_version = hop_version()

                mock_color_bold.side_effect = lambda x: f"bold({x})"
                mock_color_red.side_effect = lambda x: f"red({x})"
                mock_color_green.side_effect = lambda x: f"green({x})"

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_database_instance.state = "[Database]\n- name: test_db"
                mock_db.return_value = mock_database_instance

                mock_hgit_instance = Mock()
                mock_hgit_instance.__str__ = Mock(return_value="[Git]\n- origin: test")
                mock_hgit.return_value = mock_hgit_instance

                mock_patch_instance = Mock()
                mock_patch_instance.state = "[Patch]\n- state: ready"

                with patch('half_orm_dev.repo.Patch') as mock_patch:
                    mock_patch.return_value = mock_patch_instance

                    repo = Repo()
                    state = repo.state

                    # Should contain both version information
                    assert "hop version:" in state
                    assert "half-orm version:" in state
                    assert real_ho_version in state  # Real half_orm version
                    assert real_hop_version in state  # Real hop version

    def test_hop_version_mismatch_detection(self, temp_hop_repo):
        """Test detection of hop version mismatch."""
        from half_orm_dev.utils import hop_version

        # Create config with different version from current hop_version()
        config_file = Path(temp_hop_repo) / ".hop" / "config"
        config_content = """[halfORM]
package_name = test_db
hop_version = 0.15.0
git_origin = https://github.com/user/test.git
devel = True
"""
        config_file.write_text(config_content)

        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()

                # Should detect mismatch (config has 0.15.0, current is from hop_version())
                current_hop_version = hop_version()
                if current_hop_version != "0.15.0":
                    assert repo._Repo__hop_version_mismatch() is True
                else:
                    # If by coincidence they match, test passes
                    assert repo._Repo__hop_version_mismatch() is False

    def test_initialization_validates_repository_state(self, temp_hop_repo):
        """Test that initialization properly validates repository state."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                mock_hgit_instance = Mock()
                mock_hgit_instance.repos_is_clean.return_value = True
                mock_hgit_instance.branch = "ho-prod"
                mock_hgit.return_value = mock_hgit_instance

                repo = Repo()

                # Should have validated repo state during initialization
                assert repo.checked is True
                assert hasattr(repo, 'database')
                assert hasattr(repo, 'hgit')

    def test_config_class_integration(self, temp_hop_repo):
        """Test integration with Config class."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance

                repo = Repo()

                # Should have created Config instance and read values
                assert repo.name == "test_db"  # From config file
                assert repo.git_origin == "https://github.com/user/test.git"  # From config file
                assert repo.devel is True  # From config file
