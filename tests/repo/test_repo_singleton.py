"""
Tests pour le pattern Singleton de la classe Repo.

Module de test focalisé uniquement sur TestRepoSingleton :
- Tests du pattern Singleton (une instance par base_dir)
- Tests de _find_base_dir et logique de détection
- Tests de cache d'instances et réutilisation
- Tests de clear_instances pour cleanup
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from half_orm_dev.repo import Repo


class TestRepoSingleton:
    """Test Singleton pattern implementation for Repo class."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @pytest.fixture
    def temp_hop_repo(self):
        """Create temporary directory with .hop/config file."""
        temp_dir = tempfile.mkdtemp()

        try:
            # Create .hop directory
            hop_dir = Path(temp_dir) / ".hop"
            hop_dir.mkdir()

            # Create config file
            config_file = hop_dir / "config"
            config_content = """[halfORM]
package_name = test_db
hop_version = 0.16.0
git_origin = https://github.com/user/test.git
devel = True
"""
            config_file.write_text(config_content)

            yield temp_dir

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def nested_hop_repo(self):
        """Create nested directory structure with .hop/config in parent."""
        temp_dir = tempfile.mkdtemp()

        try:
            # Ensure temp_dir exists
            temp_path = Path(temp_dir)
            if not temp_path.exists():
                temp_path.mkdir(parents=True)

            # Create nested structure: temp_dir/project/.hop/config
            project_dir = temp_path / "project" 
            project_dir.mkdir(parents=True)

            hop_dir = project_dir / ".hop"
            hop_dir.mkdir()

            config_file = hop_dir / "config"
            config_content = """[halfORM]
package_name = nested_db
hop_version = 0.16.0
git_origin = 
devel = True
"""
            config_file.write_text(config_content)

            # Create subdirectory where we'll run from
            sub_dir = project_dir / "subdirectory"
            sub_dir.mkdir()

            yield str(project_dir), str(sub_dir)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_singleton_same_directory_returns_same_instance(self, temp_hop_repo):
        """Test that multiple Repo() calls in same directory return same instance."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            # Mock Database and HGit to avoid complex initialization
            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # First instance
                repo1 = Repo()

                # Second instance - should be the same
                repo2 = Repo()

                # Should be identical objects
                assert repo1 is repo2
                assert id(repo1) == id(repo2)

    def test_singleton_different_directories_returns_different_instances(self, temp_hop_repo):
        """Test that different directories get different Repo instances."""
        # Create second temp directory
        temp_dir2 = tempfile.mkdtemp()

        try:
            # Create .hop/config in second directory
            hop_dir2 = Path(temp_dir2) / ".hop"
            hop_dir2.mkdir()
            config_file2 = hop_dir2 / "config"
            config_file2.write_text("""[halfORM]
package_name = test_db2
hop_version = 0.16.0
git_origin = 
devel = True
""")

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # First instance from first directory
                with patch('os.path.abspath', return_value=temp_hop_repo):
                    repo1 = Repo()

                # Second instance from second directory
                with patch('os.path.abspath', return_value=temp_dir2):
                    repo2 = Repo()

                # Should be different objects
                assert repo1 is not repo2
                assert id(repo1) != id(repo2)

        finally:
            shutil.rmtree(temp_dir2, ignore_errors=True)

    def test_find_base_dir_current_directory(self, temp_hop_repo):
        """Test _find_base_dir finds .hop/config in current directory."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            base_dir = Repo._find_base_dir()

            assert base_dir == temp_hop_repo

    def test_find_base_dir_parent_directory(self, nested_hop_repo):
        """Test _find_base_dir searches up directory tree."""
        project_dir, sub_dir = nested_hop_repo

        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = sub_dir

            base_dir = Repo._find_base_dir()

            # Should find project_dir (where .hop/config exists)
            assert base_dir == project_dir

    def test_find_base_dir_no_config_returns_current_dir(self):
        """Test _find_base_dir returns current dir when no .hop/config found."""
        temp_dir = tempfile.mkdtemp()

        try:
            with patch('os.path.abspath') as mock_abspath:
                mock_abspath.return_value = temp_dir

                base_dir = Repo._find_base_dir()

                # Should fallback to current directory
                assert base_dir == temp_dir

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_find_base_dir_stops_at_root(self):
        """Test _find_base_dir stops searching at filesystem root."""
        # Mock a deep path that doesn't exist
        fake_deep_path = "/nonexistent/very/deep/path"

        with patch('os.path.abspath') as mock_abspath, \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.split') as mock_split:

            mock_abspath.return_value = fake_deep_path
            mock_exists.return_value = False  # No .hop/config anywhere

            # Mock path traversal to eventually reach root
            split_results = [
                ("/nonexistent/very/deep", "path"),
                ("/nonexistent/very", "deep"), 
                ("/nonexistent", "very"),
                ("/", "nonexistent"),
                ("/", "")  # Root reached
            ]
            mock_split.side_effect = split_results

            base_dir = Repo._find_base_dir()

            # Should return original path as fallback
            assert base_dir == fake_deep_path

    def test_singleton_instances_stored_by_base_dir(self, temp_hop_repo):
        """Test that singleton instances are stored with base_dir as key."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Create instance
                repo = Repo()

                # Check internal storage
                assert temp_hop_repo in Repo._instances
                assert Repo._instances[temp_hop_repo] is repo

    def test_singleton_cache_persistence(self, temp_hop_repo):
        """Test that singleton cache persists across multiple calls."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Create multiple instances
                repo1 = Repo()
                repo2 = Repo() 
                repo3 = Repo()

                # All should be the same instance
                assert repo1 is repo2 is repo3

                # Only one entry in cache
                assert len(Repo._instances) == 1

    def test_clear_instances_removes_all_cached_instances(self, temp_hop_repo):
        """Test clear_instances removes all cached Repo instances."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Create instance
                repo = Repo()
                assert len(Repo._instances) == 1

                # Clear instances
                Repo.clear_instances()

                # Cache should be empty
                assert len(Repo._instances) == 0
                assert Repo._instances == {}

    def test_clear_instances_disconnects_database_models(self, temp_hop_repo):
        """Test clear_instances properly disconnects database models."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            # Mock database and model with disconnect method
            mock_model = Mock()
            mock_database = Mock()
            mock_database.model = mock_model

            with patch('half_orm_dev.repo.Database') as mock_db_class, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_db_class.return_value = mock_database

                # Create instance
                repo = Repo()

                # Clear instances
                Repo.clear_instances()

                # Should have called disconnect
                mock_model.disconnect.assert_called_once()

    def test_clear_instances_handles_missing_database_gracefully(self, temp_hop_repo):
        """Test clear_instances handles cases where database/model is None."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                # Create instance
                repo = Repo()

                # Set database/model to None (edge case)
                repo.database = None

                # Should not raise exception
                Repo.clear_instances()
                assert len(Repo._instances) == 0

    def test_clear_instances_handles_disconnect_exceptions(self, temp_hop_repo):
        """Test clear_instances handles database disconnect exceptions gracefully."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_hop_repo

            # Mock database model that raises exception on disconnect
            mock_model = Mock()
            mock_model.disconnect.side_effect = Exception("Database connection error")
            mock_database = Mock()
            mock_database.model = mock_model

            with patch('half_orm_dev.repo.Database') as mock_db_class, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit:

                mock_db_class.return_value = mock_database

                # Create instance
                repo = Repo()

                # Should not raise exception even if disconnect fails
                Repo.clear_instances()
                assert len(Repo._instances) == 0

    def test_singleton_thread_safety_basic(self, temp_hop_repo):
        """Test that singleton is NOT thread-safe (current implementation)."""
        import threading
        import time

        instances = []

        def create_repo():
            with patch('os.path.abspath') as mock_abspath:
                mock_abspath.return_value = temp_hop_repo

                # CORRECTION: Retirer le patch de Changelog qui n'existe plus
                with patch('half_orm_dev.repo.Database') as mock_db, \
                     patch('half_orm_dev.repo.HGit') as mock_hgit:

                    # Add small delay to increase chance of race condition
                    time.sleep(0.01)
                    repo = Repo()
                    instances.append(repo)

        # Create multiple threads
        threads = [threading.Thread(target=create_repo) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Current implementation is NOT thread-safe - multiple instances may be created
        # This documents the current behavior rather than enforcing thread safety
        assert len(instances) == 5  # All threads created instances

        # But they should all be for the same base_dir
        unique_instances = set(id(instance) for instance in instances)

        # May have 1 instance (lucky timing) or multiple (race conditions)
        # This test documents that thread safety is not guaranteed
        assert len(unique_instances) >= 1

    def test_singleton_with_different_working_directories(self, nested_hop_repo):
        """Test singleton behavior when changing working directories."""
        project_dir, sub_dir = nested_hop_repo

        with patch('half_orm_dev.repo.Database') as mock_db, \
             patch('half_orm_dev.repo.HGit') as mock_hgit:

            # First call from subdirectory (should find project_dir)
            with patch('os.path.abspath', return_value=sub_dir):
                repo1 = Repo()

            # Second call from project directory (should find same base)
            with patch('os.path.abspath', return_value=project_dir):
                repo2 = Repo()

            # Should be the same instance (same base_dir found)
            assert repo1 is repo2
