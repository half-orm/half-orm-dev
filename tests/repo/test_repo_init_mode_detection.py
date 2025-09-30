"""
Tests for Repo.init_git_centric_project() - Mode detection phase

Focused on:
- Automatic development mode detection (_detect_development_mode)
- Metadata presence verification
- Full development mode vs sync-only mode
"""

import pytest
from unittest.mock import Mock, patch
from half_orm.model_errors import UnknownRelation

from half_orm_dev.repo import Repo


class TestDevelopmentModeDetection:
    """Test _detect_development_mode() method."""

    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()

    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()

    @patch('half_orm.model.Model')
    def test_detect_development_mode_with_metadata_returns_true(self, mock_model):
        """Test detection returns True when metadata schemas exist."""
        # Setup mock
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock has_relation to return True (metadata exists)
        mock_model_instance.has_relation.return_value = True

        # Create bare Repo instance
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False

        # Should return True (full development mode)
        result = repo._detect_development_mode("my_blog")

        assert result is True

        # Should check for metadata table
        mock_model.assert_called_once_with("my_blog")
        mock_model_instance.has_relation.assert_called_once_with('half_orm_meta.hop_release')

    @patch('half_orm.model.Model')
    def test_detect_development_mode_without_metadata_returns_false(self, mock_model):
        """Test detection returns False when metadata schemas don't exist."""
        # Setup mock
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance

        # Mock has_relation to return False (metadata doesn't exist)
        mock_model_instance.has_relation.return_value = False

        # Create bare Repo instance
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False

        # Should return False (sync-only mode)
        result = repo._detect_development_mode("legacy_db")

        assert result is False

        # Should have attempted metadata check
        mock_model.assert_called_once_with("legacy_db")
        mock_model_instance.has_relation.assert_called_once_with('half_orm_meta.hop_release')

    @patch('half_orm.model.Model')
    def test_detect_development_mode_stores_model_instance(self, mock_model):
        """Test that Model instance is reused, not recreated."""
        # Setup mock
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance
        mock_model_instance.has_relation.return_value = True

        # Create bare Repo instance
        repo = Repo.__new__(Repo)
        repo._Repo__checked = False

        # Call detection
        repo._detect_development_mode("my_blog")

        # Model should only be created once (efficiency)
        mock_model.assert_called_once_with("my_blog")

    @patch('half_orm.model.Model')
    def test_detect_development_mode_multiple_databases(self, mock_model):
        """Test detection works correctly for different databases."""
        # Setup mocks for two different databases
        mock_model_with_metadata = Mock()
        mock_model_with_metadata.has_relation.return_value = True

        mock_model_without_metadata = Mock()
        mock_model_without_metadata.has_relation.return_value = False

        # First call: database with metadata
        mock_model.return_value = mock_model_with_metadata
        repo1 = Repo.__new__(Repo)
        repo1._Repo__checked = False
        result1 = repo1._detect_development_mode("dev_db")

        # Second call: database without metadata
        mock_model.return_value = mock_model_without_metadata
        repo2 = Repo.__new__(Repo)
        repo2._Repo__checked = False
        result2 = repo2._detect_development_mode("legacy_db")

        # Results should differ based on metadata presence
        assert result1 is True   # dev_db has metadata
        assert result2 is False  # legacy_db lacks metadata

    @patch('half_orm.model.Model')
    def test_detect_development_mode_checks_specific_table(self, mock_model):
        """Test that detection checks specifically for hop_release table."""
        mock_model_instance = Mock()
        mock_model.return_value = mock_model_instance
        mock_model_instance.has_relation.return_value = True

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False

        repo._detect_development_mode("test_db")

        # Must check for the exact metadata table
        mock_model_instance.has_relation.assert_called_with('half_orm_meta.hop_release')

    @patch('half_orm.model.Model')
    def test_detect_development_mode_connection_already_exists(self, mock_model):
        """Test detection when Model instance already exists in repo."""
        # Simulate scenario where _verify_database_configured already created Model
        existing_model = Mock()
        existing_model.has_relation.return_value = True

        repo = Repo.__new__(Repo)
        repo._Repo__checked = False
        repo.database = Mock()
        repo.database.model = existing_model

        # Detection should reuse existing model, not create new one
        result = repo._detect_development_mode("my_blog")

        assert result is True

        # Should NOT call Model() constructor again
        mock_model.assert_not_called()

        # Should use existing model
        existing_model.has_relation.assert_called_once_with('half_orm_meta.hop_release')

    def test_detect_development_mode_handles_other_exceptions(self):
        """Test that exceptions from has_relation() are propagated."""
        # Note: has_relation() returns boolean, doesn't raise exceptions
        # This test documents that any unexpected Model() exceptions propagate

        from half_orm.model import Model

        with patch('half_orm.model.Model') as mock_model:
            # Simulate Model creation failure
            mock_model.side_effect = Exception("Database connection error")

            repo = Repo.__new__(Repo)
            repo._Repo__checked = False

            # Should propagate Model creation exceptions
            with pytest.raises(Exception, match="Database connection error"):
                repo._detect_development_mode("test_db")