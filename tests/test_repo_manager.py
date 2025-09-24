"""
Tests pour l'intégration PatchManager dans Repo.

Module de test focalisé sur l'intégration du PatchManager dans la classe Repo :
- Tests de la propriété patch_manager (lazy initialization, cache)
- Tests des méthodes de support (has_patch_directory_support, clear_patch_directory_cache)
- Tests d'intégration fonctionnelle avec création/validation/application de patches
- Tests de gestion d'erreurs et validation des modes (devel requis)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from half_orm_dev.repo import Repo
from half_orm_dev.patch_manager import PatchManager, PatchManagerError


# Fixtures au niveau module (accessibles à toutes les classes)

@pytest.fixture
def temp_devel_repo():
    """Create temporary development repository."""
    from half_orm_dev.utils import hop_version
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create .hop directory
        hop_dir = Path(temp_dir) / ".hop"
        hop_dir.mkdir(exist_ok=True)
        
        # Create devel config
        current_hop_version = hop_version()
        config_file = hop_dir / "config"
        config_content = f"""[halfORM]
package_name = test_devel_db
hop_version = {current_hop_version}
git_origin = https://github.com/user/test.git
devel = True
"""
        config_file.write_text(config_content)
        
        yield temp_dir
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def temp_non_devel_repo():
    """Create temporary non-development repository."""
    from half_orm_dev.utils import hop_version
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create .hop directory
        hop_dir = Path(temp_dir) / ".hop"
        hop_dir.mkdir(exist_ok=True)
        
        # Create non-devel config
        current_hop_version = hop_version()
        config_file = hop_dir / "config"
        config_content = f"""[halfORM]
package_name = test_prod_db
hop_version = {current_hop_version}
git_origin = https://github.com/company/prod.git
devel = False
"""
        config_file.write_text(config_content)
        
        yield temp_dir
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def devel_repo(temp_devel_repo):
    """Create Repo instance in development mode."""
    # Clear instances before creating new one
    Repo.clear_instances()
    
    with patch('os.path.abspath') as mock_abspath:
        mock_abspath.return_value = temp_devel_repo
        
        with patch('half_orm_dev.repo.Database') as mock_db, \
             patch('half_orm_dev.repo.HGit') as mock_hgit, \
             patch('half_orm_dev.repo.Changelog') as mock_changelog:
            
            mock_database_instance = Mock()
            mock_database_instance.production = False
            mock_db.return_value = mock_database_instance
            
            repo = Repo()
            yield repo

@pytest.fixture
def non_devel_repo(temp_non_devel_repo):
    """Create Repo instance in non-development mode."""
    # Clear instances before creating new one
    Repo.clear_instances()
    
    with patch('os.path.abspath') as mock_abspath:
        mock_abspath.return_value = temp_non_devel_repo
        
        with patch('half_orm_dev.repo.Database') as mock_db:
            mock_database_instance = Mock()
            mock_database_instance.production = True
            mock_db.return_value = mock_database_instance
            
            repo = Repo()
            yield repo


class TestRepoPatchManagerIntegration:
    """Test intégration PatchManager dans Repo."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()


class TestPatchManagerProperty:
    """Test la propriété patch_manager de Repo."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()
    
    def test_patch_manager_lazy_initialization(self, devel_repo):
        """Test lazy initialization of PatchManager."""
        repo = devel_repo
        
        # Initially, patch manager should not be created
        assert repo._patch_directory is None
        
        # First access should create and cache instance
        patch_mgr = repo.patch_manager
        assert isinstance(patch_mgr, PatchManager)
        assert repo._patch_directory is patch_mgr
        
        # Second access should return cached instance
        patch_mgr2 = repo.patch_manager
        assert patch_mgr2 is patch_mgr
    
    def test_patch_manager_requires_devel_mode(self, non_devel_repo):
        """Test PatchManager requires development mode."""
        repo = non_devel_repo
        
        with pytest.raises(PatchManagerError, match="development mode"):
            _ = repo.patch_manager
    
    def test_patch_manager_requires_checked_repo(self):
        """Test PatchManager requires properly initialized repository."""
        # Create unchecked repo (no .hop/config found)
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = "/nonexistent/path"
            
            repo = Repo()
            assert repo.checked is False
            
            with pytest.raises(RuntimeError, match="Repository not initialized"):
                _ = repo.patch_manager
    
    def test_patch_manager_handles_initialization_failure(self, devel_repo):
        """Test PatchManager handles initialization failures."""
        repo = devel_repo
        
        # Mock PatchManager to raise exception during init
        with patch('half_orm_dev.repo.PatchManager') as mock_pm:
            mock_pm.side_effect = Exception("Initialization failed")
            
            with pytest.raises(PatchManagerError, match="Failed to initialize"):
                _ = repo.patch_manager
    
    def test_patch_manager_integration_with_real_paths(self, devel_repo):
        """Test PatchManager integration with real repository paths."""
        repo = devel_repo
        
        # Should create PatchManager with correct repo reference
        patch_mgr = repo.patch_manager
        
        # PatchManager should have repo reference
        assert patch_mgr._repo is repo
        assert patch_mgr._base_dir == repo.base_dir
        assert patch_mgr._repo_name == repo.name
        
        # Should have created Patches directory
        patches_dir = Path(repo.base_dir) / "Patches"
        assert patches_dir.exists()
        assert patches_dir.is_dir()


class TestPatchManagerSupport:
    """Test méthodes de support PatchManager."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()
    
    def test_has_patch_directory_support_devel_mode(self, devel_repo):
        """Test has_patch_directory_support returns True for devel repo."""
        repo = devel_repo
        assert repo.has_patch_directory_support() is True
    
    def test_has_patch_directory_support_non_devel_mode(self, non_devel_repo):
        """Test has_patch_directory_support returns False for non-devel repo."""
        repo = non_devel_repo
        assert repo.has_patch_directory_support() is False
    
    def test_has_patch_directory_support_unchecked_repo(self):
        """Test has_patch_directory_support returns False for unchecked repo."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = "/nonexistent/path"
            
            repo = Repo()
            assert repo.checked is False
            assert repo.has_patch_directory_support() is False
    
    def test_clear_patch_directory_cache(self, devel_repo):
        """Test clearing PatchManager cache."""
        repo = devel_repo
        
        # Create cached instance
        patch_mgr1 = repo.patch_manager
        assert repo._patch_directory is patch_mgr1
        
        # Clear cache
        repo.clear_patch_directory_cache()
        assert repo._patch_directory is None
        
        # Next access should create new instance
        patch_mgr2 = repo.patch_manager
        assert patch_mgr2 is not patch_mgr1
    
    def test_clear_patch_directory_cache_when_none(self, devel_repo):
        """Test clearing cache when no instance exists."""
        repo = devel_repo
        
        # Initially no instance
        assert repo._patch_directory is None
        
        # Should not raise exception
        repo.clear_patch_directory_cache()
        assert repo._patch_directory is None


class TestPatchManagerFunctionalIntegration:
    """Test intégration fonctionnelle complète."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()
    
    def test_create_patch_directory_integration(self, devel_repo):
        """Test création de patch directory via Repo."""
        repo = devel_repo
        
        # Create patch directory
        patch_path = repo.patch_manager.create_patch_directory("456-user-auth")
        
        # Verify creation
        expected_path = Path(repo.base_dir) / "Patches" / "456-user-auth"
        assert patch_path == expected_path
        assert patch_path.exists()
        assert patch_path.is_dir()
        
        # Verify README.md
        readme_path = patch_path / "README.md"
        assert readme_path.exists()
        assert readme_path.read_text() == "# Patch 456-user-auth\n"
    
    def test_get_patch_structure_integration(self, devel_repo):
        """Test analyse de structure de patch via Repo."""
        repo = devel_repo
        
        # Create patch with files
        patch_path = repo.patch_manager.create_patch_directory("789-test")
        (patch_path / "01_create.sql").write_text("CREATE TABLE test (id INTEGER);")
        (patch_path / "02_script.py").write_text("print('test')")
        
        # Analyze structure
        structure = repo.patch_manager.get_patch_structure("789-test")
        
        assert structure.is_valid is True
        assert len(structure.files) == 2
        assert structure.files[0].name == "01_create.sql"
        assert structure.files[0].is_sql is True
        assert structure.files[1].name == "02_script.py"
        assert structure.files[1].is_python is True
    
    def test_list_all_patches_integration(self, devel_repo):
        """Test listing patches via Repo."""
        repo = devel_repo
        
        # Create multiple patches
        patch_ids = ["123-first", "456-second", "789-third"]
        for patch_id in patch_ids:
            repo.patch_manager.create_patch_directory(patch_id)
        
        # List all patches
        found_patches = repo.patch_manager.list_all_patches()
        
        assert len(found_patches) == 3
        assert set(found_patches) == set(patch_ids)
    
    def test_apply_patch_files_integration(self, devel_repo):
        """Test application de patches via Repo."""
        repo = devel_repo
        
        # Create patch with SQL and Python files
        patch_path = repo.patch_manager.create_patch_directory("999-apply-test")
        (patch_path / "01_table.sql").write_text("CREATE TABLE users (id INTEGER);")
        (patch_path / "02_data.sql").write_text("INSERT INTO users VALUES (1);")
        (patch_path / "03_script.py").write_text("print('Migration complete')")
        
        # Mock database model
        mock_database = Mock()
        mock_database.execute_query = Mock()
        
        # Apply patch files
        applied_files = repo.patch_manager.apply_patch_files("999-apply-test", mock_database)
        
        # Verify application
        expected_files = ["01_table.sql", "02_data.sql", "03_script.py"]
        assert applied_files == expected_files
        
        # Verify SQL execution
        assert mock_database.execute_query.call_count == 2  # Two SQL files
    
    def test_delete_patch_directory_integration(self, devel_repo):
        """Test suppression de patch directory via Repo."""
        repo = devel_repo
        
        # Create patch
        patch_path = repo.patch_manager.create_patch_directory("888-delete-me")
        assert patch_path.exists()
        
        # Delete patch
        result = repo.patch_manager.delete_patch_directory("888-delete-me", confirm=True)
        
        assert result is True
        assert not patch_path.exists()
    
    def test_patch_manager_error_propagation(self, devel_repo):
        """Test propagation des erreurs PatchManager."""
        repo = devel_repo
        
        # Test création patch avec ID invalide
        with pytest.raises(PatchManagerError, match="Invalid patch ID"):
            repo.patch_manager.create_patch_directory("invalid@patch")
        
        # Test structure patch inexistant
        with pytest.raises(PatchManagerError, match="Cannot apply invalid patch"):
            mock_db = Mock()
            repo.patch_manager.apply_patch_files("nonexistent-patch", mock_db)


class TestPatchManagerIntegrationEdgeCases:
    """Test cas limites d'intégration PatchManager."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()
    
    def test_patch_manager_after_repo_configuration_change(self, temp_devel_repo):
        """Test PatchManager après changement configuration repo."""
        with patch('os.path.abspath') as mock_abspath:
            mock_abspath.return_value = temp_devel_repo
            
            with patch('half_orm_dev.repo.Database') as mock_db, \
                 patch('half_orm_dev.repo.HGit') as mock_hgit, \
                 patch('half_orm_dev.repo.Changelog') as mock_changelog:
                
                # Start with devel=True
                mock_database_instance = Mock()
                mock_database_instance.production = False
                mock_db.return_value = mock_database_instance
                
                repo = Repo()
                
                # Access patch manager (should work)
                patch_mgr1 = repo.patch_manager
                assert isinstance(patch_mgr1, PatchManager)
                
                # Simulate config change to devel=False by patching the underlying config
                # Note: In real scenario, this would require repo restart
                with patch.object(repo, '_Repo__config') as mock_config:
                    mock_config.devel = False
                    
                    # Clear cache to force re-check
                    repo.clear_patch_directory_cache()
                    
                    # Should fail now
                    with pytest.raises(PatchManagerError, match="development mode"):
                        _ = repo.patch_manager
    
    def test_patch_manager_with_patches_directory_permissions(self, devel_repo):
        """Test PatchManager avec problèmes permissions Patches directory."""
        repo = devel_repo
        
        # Create Patches directory manually
        patches_dir = Path(repo.base_dir) / "Patches"
        patches_dir.mkdir(exist_ok=True)
        
        # Make it read-only
        patches_dir.chmod(0o444)
        
        try:
            # Should still be able to access patch manager
            patch_mgr = repo.patch_manager
            assert isinstance(patch_mgr, PatchManager)
            
            # But creating patches should fail
            with pytest.raises(PatchManagerError, match="Permission denied"):
                patch_mgr.create_patch_directory("456-permission-test")
                
        finally:
            # Restore permissions for cleanup
            patches_dir.chmod(0o755)
    
    def test_patch_manager_singleton_consistency(self, devel_repo):
        """Test cohérence Singleton entre Repo et PatchManager."""
        repo1 = devel_repo
        
        # Get patch manager from first repo
        patch_mgr1 = repo1.patch_manager
        
        # Get second repo instance (should be same due to singleton)
        repo2 = Repo()  # Same base_dir due to mocking
        assert repo2 is repo1  # Singleton behavior
        
        # Patch manager should be same cached instance
        patch_mgr2 = repo2.patch_manager
        assert patch_mgr2 is patch_mgr1
    
    def test_patch_manager_integration_with_model_property(self, devel_repo):
        """Test intégration PatchManager avec propriété model de Repo."""
        repo = devel_repo
        
        # Mock model for apply_patch_files
        mock_model = Mock()
        mock_model.execute_query = Mock()
        
        # Patch the underlying database.model instead of repo.model
        with patch.object(repo.database, 'model', mock_model):
            # Create and apply patch
            patch_path = repo.patch_manager.create_patch_directory("777-model-test")
            (patch_path / "01_test.sql").write_text("SELECT 1;")
            
            # Apply using repo.model (which delegates to database.model)
            applied_files = repo.patch_manager.apply_patch_files("777-model-test", repo.model)
            
            assert applied_files == ["01_test.sql"]
            repo.model.execute_query.assert_called_once_with("SELECT 1;")
    
    def test_patch_manager_memory_cleanup_on_clear_cache(self, devel_repo):
        """Test nettoyage mémoire lors du clear cache."""
        repo = devel_repo
        
        # Create patch manager and add some operations
        patch_mgr = repo.patch_manager
        patch_mgr.create_patch_directory("555-memory-test")
        
        # Clear cache
        repo.clear_patch_directory_cache()
        
        # New patch manager should be independent
        new_patch_mgr = repo.patch_manager
        assert new_patch_mgr is not patch_mgr
        
        # Should still be able to see existing patches
        patches = new_patch_mgr.list_all_patches()
        assert "555-memory-test" in patches


class TestPatchManagerDocumentationExamples:
    """Test exemples de la documentation PatchManager."""
    
    def setup_method(self):
        """Clear singleton instances before each test."""
        Repo.clear_instances()
    
    def teardown_method(self):
        """Clear singleton instances after each test."""
        Repo.clear_instances()
    
    def test_documentation_example_basic_usage(self, devel_repo):
        """Test exemple basique de la documentation."""
        repo = devel_repo
        
        # Example from repo.py docstring
        # Create new patch directory
        repo.patch_manager.create_patch_directory("456-user-auth")

        # Apply patch files using repo's model
        mock_model = Mock()
        mock_model.execute_query = Mock()
        
        # Create test files
        patch_path = Path(repo.base_dir) / "Patches" / "456-user-auth"
        (patch_path / "01_create.sql").write_text("CREATE TABLE users (id INTEGER);")
        
        applied = repo.patch_manager.apply_patch_files("456-user-auth", mock_model)
        assert applied == ["01_create.sql"]

        # List all existing patches
        patches = repo.patch_manager.list_all_patches()
        assert "456-user-auth" in patches

        # Get detailed patch structure analysis
        structure = repo.patch_manager.get_patch_structure("456-user-auth")
        assert structure.is_valid is True
        assert len(structure.files) == 1
    
    def test_documentation_example_error_handling(self, non_devel_repo):
        """Test exemple gestion d'erreurs de la documentation."""
        repo = non_devel_repo
        
        # Example from repo.py docstring - should raise PatchManagerError
        with pytest.raises(PatchManagerError, match="development mode"):
            repo.patch_manager.create_patch_directory("456-user-auth")
    
    def test_documentation_example_support_check(self, devel_repo, non_devel_repo):
        """Test exemple vérification support de la documentation."""
        # Example from repo.py docstring
        
        # Devel repo should support patch operations
        if devel_repo.has_patch_directory_support():
            patches = devel_repo.patch_manager.list_all_patches()
            assert isinstance(patches, list)
        
        # Non-devel repo should not support patch operations
        if not non_devel_repo.has_patch_directory_support():
            # Should not try to access patch_manager
            assert non_devel_repo.has_patch_directory_support() is False