"""
Tests pour l'initialisation de PatchManager.

Module de test focalisé sur la validation de l'initialisation correcte
de la classe PatchManager avec différents types de repository.
"""

import pytest
from unittest.mock import Mock
from pathlib import Path

from half_orm_dev.patch_manager import (
    PatchManager, 
    PatchManagerError
)


class TestPatchDirectoryInitialization:
    """Test PatchManager initialization and validation."""

    def test_init_with_valid_repo(self, temp_repo):
        """Test initialization with valid repository."""
        repo, temp_dir, patches_dir = temp_repo
        
        patch_mgr = PatchManager(repo)
        
        # Should initialize without errors
        assert patch_mgr is not None
        
        # Should store repo reference
        assert hasattr(patch_mgr, '_repo')
        assert patch_mgr._repo == repo
        
        # Should have access to base directory
        assert hasattr(patch_mgr, '_base_dir')
        assert patch_mgr._base_dir == temp_dir
        
        # Should have PatchValidator instance
        assert hasattr(patch_mgr, '_validator')

    def test_init_with_none_repo(self):
        """Test initialization with None repository."""
        with pytest.raises(PatchManagerError, match="Repository cannot be None"):
            PatchManager(None)

    def test_init_with_invalid_repo_missing_base_dir(self):
        """Test initialization with repository missing base_dir."""
        invalid_repo = Mock()
        invalid_repo.base_dir = None
        invalid_repo.devel = True
        
        with pytest.raises(PatchManagerError, match="Repository is invalid"):
            PatchManager(invalid_repo)

    def test_init_with_invalid_repo_missing_devel_flag(self):
        """Test initialization with repository missing devel flag."""
        invalid_repo = Mock()
        invalid_repo.base_dir = "/tmp/test"
        # Missing devel attribute
        del invalid_repo.devel
        
        with pytest.raises(PatchManagerError, match="Repository is invalid"):
            PatchManager(invalid_repo)

    def test_init_nonexistent_base_dir(self):
        """Test initialization with nonexistent base directory."""
        repo = Mock()
        repo.base_dir = "/nonexistent/path/that/should/not/exist"
        repo.devel = True
        
        with pytest.raises(PatchManagerError, match="Base directory does not exist"):
            PatchManager(repo)

    def test_init_base_dir_not_directory(self, temp_repo):
        """Test initialization when base_dir points to a file, not directory."""
        repo, temp_dir, patches_dir = temp_repo
        
        # Create a file instead of directory
        file_path = Path(temp_dir) / "not_a_directory"
        file_path.write_text("This is a file, not a directory")
        
        repo.base_dir = str(file_path)
        
        with pytest.raises(PatchManagerError, match="Base directory.*not a directory"):
            PatchManager(repo)

    def test_init_missing_schema_patches_directory(self, temp_repo):
        """Test initialization when Patches directory doesn't exist."""
        repo, temp_dir, patches_dir = temp_repo
        
        # Remove the Patches directory
        patches_dir.rmdir()
        
        # Should create Patches directory automatically
        patch_mgr = PatchManager(repo)
        
        assert patch_mgr is not None
        assert patches_dir.exists()
        assert patches_dir.is_dir()

    def test_init_schema_patches_is_file(self, temp_repo):
        """Test initialization when Patches exists but is a file."""
        repo, temp_dir, patches_dir = temp_repo
        
        # Remove directory and create file with same name
        patches_dir.rmdir()
        schema_patches_file = Path(temp_dir) / "Patches"
        schema_patches_file.write_text("This should be a directory")
        
        with pytest.raises(PatchManagerError, match="Patches.*not a directory"):
            PatchManager(repo)

    def test_init_no_permission_to_create_schema_patches(self, temp_repo):
        """Test initialization when no permission to create Patches."""
        repo, temp_dir, patches_dir = temp_repo
        
        # Remove Patches directory
        patches_dir.rmdir()
        
        # Make base directory read-only
        Path(temp_dir).chmod(0o444)
        
        try:
            with pytest.raises(PatchManagerError, match="Permission denied"):
                PatchManager(repo)
        finally:
            # Restore permissions for cleanup
            Path(temp_dir).chmod(0o755)

    def test_init_stores_correct_paths(self, temp_repo):
        """Test that initialization stores correct internal paths."""
        repo, temp_dir, patches_dir = temp_repo
        
        patch_mgr = PatchManager(repo)
        
        # Should store base directory path
        assert patch_mgr._base_dir == temp_dir
        
        # Should calculate schema patches path correctly
        expected_schema_path = Path(temp_dir) / "Patches"
        assert patch_mgr._schema_patches_dir == expected_schema_path
        
        # Paths should be Path objects, not strings
        assert isinstance(patch_mgr._schema_patches_dir, Path)

    def test_init_validator_integration(self, temp_repo):
        """Test that PatchValidator is properly initialized."""
        repo, temp_dir, patches_dir = temp_repo
        
        patch_mgr = PatchManager(repo)
        
        # Should have validator instance
        assert hasattr(patch_mgr, '_validator')
        assert patch_mgr._validator is not None
        
        # Validator should be functional
        # Test basic validation call
        patch_info = patch_mgr._validator.validate_patch_id("456")
        assert patch_info.ticket_number == "456"

    def test_init_with_repo_name_storage(self, temp_repo):
        """Test that repository name is properly stored."""
        repo, temp_dir, patches_dir = temp_repo
        repo.name = "custom_database_name"
        
        patch_mgr = PatchManager(repo)
        
        # Should store repo name for use in templates
        assert patch_mgr._repo_name == "custom_database_name"

    def test_init_with_missing_repo_name(self, temp_repo):
        """Test initialization with repository missing name attribute."""
        repo, temp_dir, patches_dir = temp_repo
        del repo.name  # Remove name attribute
        
        # Should fail because name is required
        with pytest.raises(PatchManagerError, match="missing 'name' attribute"):
            PatchManager(repo)

    def test_init_multiple_instances_different_repos(self):
        """Test creating multiple PatchManager instances with different repos."""
        import tempfile
        
        # Create two different temp repos
        temp_dir1 = tempfile.mkdtemp()
        temp_dir2 = tempfile.mkdtemp()
        
        try:
            # Create schema patches directories
            (Path(temp_dir1) / "Patches").mkdir()
            (Path(temp_dir2) / "Patches").mkdir()
            
            repo1 = Mock()
            repo1.base_dir = temp_dir1
            repo1.name = "database1"
            repo1.devel = True
            
            repo2 = Mock()
            repo2.base_dir = temp_dir2  
            repo2.name = "database2"
            repo2.devel = True
            
            patch_dir1 = PatchManager(repo1)
            patch_dir2 = PatchManager(repo2)
            
            # Should be separate instances with different configs
            assert patch_dir1._base_dir != patch_dir2._base_dir
            assert patch_dir1._repo_name != patch_dir2._repo_name
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir1)
            shutil.rmtree(temp_dir2)

    def test_init_repo_validation_comprehensive(self):
        """Test comprehensive repository validation during initialization."""
        # Test all required attributes are checked
        required_attrs = ['base_dir', 'devel', 'name']
        
        for missing_attr in required_attrs:
            repo = Mock()
            repo.base_dir = "/tmp/test"
            repo.devel = True
            repo.name = "test_db"
            
            # Remove the specific attribute
            delattr(repo, missing_attr)
            
            with pytest.raises(PatchManagerError):
                PatchManager(repo)
