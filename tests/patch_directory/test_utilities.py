"""
Tests pour les méthodes utilitaires de PatchDirectory.

Module de test focalisé sur les méthodes utilitaires simples comme
get_patch_directory_path, list_all_patches, et delete_patch_directory.
"""

import pytest
from pathlib import Path

from half_orm_dev.patch_directory import (
    PatchDirectory,
    PatchDirectoryError
)


class TestGetPatchDirectoryPath:
    """Test patch directory path operations."""

    def test_get_patch_directory_path_valid_id(self, patch_directory):
        """Test getting path for valid patch ID."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        path = patch_dir.get_patch_directory_path("456-user-auth")
        
        expected_path = schema_patches_dir / "456-user-auth"
        assert path == expected_path
        assert isinstance(path, Path)

    def test_get_patch_directory_path_numeric_id(self, patch_directory):
        """Test getting path for numeric patch ID."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        path = patch_dir.get_patch_directory_path("456")
        
        expected_path = schema_patches_dir / "456"
        assert path == expected_path

    def test_get_patch_directory_path_complex_id(self, patch_directory):
        """Test getting path for complex patch ID with multiple hyphens."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        path = patch_dir.get_patch_directory_path("456-user-auth-system")
        
        expected_path = schema_patches_dir / "456-user-auth-system"
        assert path == expected_path

    def test_get_patch_directory_path_does_not_validate_existence(self, patch_directory):
        """Test that method doesn't validate directory existence."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Should return path even for nonexistent patch
        path = patch_dir.get_patch_directory_path("nonexistent")
        
        expected_path = schema_patches_dir / "nonexistent"
        assert path == expected_path
        assert not path.exists()  # Doesn't exist but method still returns path

    def test_get_patch_directory_path_empty_id(self, patch_directory):
        """Test getting path for empty patch ID."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        path = patch_dir.get_patch_directory_path("")
        
        # Should return path to SchemaPatches directory itself
        expected_path = schema_patches_dir / ""
        assert path == expected_path

    def test_get_patch_directory_path_whitespace_handling(self, patch_directory):
        """Test path generation handles whitespace correctly."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Should handle patch IDs with leading/trailing whitespace
        path = patch_dir.get_patch_directory_path("  456-user-auth  ")
        
        # Path should be normalized (whitespace stripped)
        expected_path = schema_patches_dir / "456-user-auth"
        assert path == expected_path


class TestListAllPatches:
    """Test listing all patch directories."""

    def test_list_all_patches_multiple_patches(self, patch_directory):
        """Test listing multiple valid patches."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create multiple patch directories
        patches = ["456-user-auth", "789-security-fix", "234-performance"]
        for patch_id in patches:
            patch_path = schema_patches_dir / patch_id
            patch_path.mkdir()
            (patch_path / "README.md").write_text(f"# {patch_id}")
        
        found_patches = patch_dir.list_all_patches()
        
        # Should return all valid patches
        assert len(found_patches) == 3
        assert set(found_patches) == set(patches)

    def test_list_all_patches_empty_schema_patches(self, patch_directory):
        """Test listing patches in empty SchemaPatches directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        found_patches = patch_dir.list_all_patches()
        
        # Should return empty list
        assert found_patches == []

    def test_list_all_patches_filters_invalid_directories(self, patch_directory):
        """Test that invalid directories are filtered out."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create mix of valid and invalid directories
        (schema_patches_dir / "456-valid").mkdir()
        (schema_patches_dir / "456-valid" / "README.md").write_text("# Valid")
        
        (schema_patches_dir / "invalid-format").mkdir()  # No number prefix
        (schema_patches_dir / "__pycache__").mkdir()     # Python cache
        (schema_patches_dir / ".hidden").mkdir()         # Hidden directory
        
        # Create a file (not directory)
        (schema_patches_dir / "not-a-directory.txt").write_text("Not a directory")
        
        found_patches = patch_dir.list_all_patches()
        
        # Should return only valid patches
        assert found_patches == ["456-valid"]

    def test_list_all_patches_sorted_order(self, patch_directory):
        """Test patches are returned in sorted order."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patches in random order
        patches = ["999-last", "123-first", "456-middle", "789-another"]
        for patch_id in patches:
            patch_path = schema_patches_dir / patch_id
            patch_path.mkdir()
            (patch_path / "README.md").write_text(f"# {patch_id}")
        
        found_patches = patch_dir.list_all_patches()
        
        # Should be sorted by patch number
        expected_order = ["123-first", "456-middle", "789-another", "999-last"]
        assert found_patches == expected_order

    def test_list_all_patches_numeric_vs_full_ids(self, patch_directory):
        """Test listing mix of numeric and full patch IDs."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create mix of numeric and full IDs
        patches = ["123", "456-user-auth", "789", "234-security-fix"]
        for patch_id in patches:
            patch_path = schema_patches_dir / patch_id
            patch_path.mkdir()
            (patch_path / "README.md").write_text(f"# {patch_id}")
        
        found_patches = patch_dir.list_all_patches()
        
        # Should be sorted numerically
        expected_order = ["123", "234-security-fix", "456-user-auth", "789"]
        assert found_patches == expected_order

    def test_list_all_patches_filters_incomplete_patches(self, patch_directory):
        """Test filtering out patches without required files."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create valid patch
        valid_path = schema_patches_dir / "456-valid"
        valid_path.mkdir()
        (valid_path / "README.md").write_text("# Valid patch")
        
        # Create incomplete patch (no README)
        incomplete_path = schema_patches_dir / "789-incomplete"
        incomplete_path.mkdir()
        (incomplete_path / "01_test.sql").write_text("SELECT 1;")
        # Missing README.md
        
        found_patches = patch_dir.list_all_patches()
        
        # Should only return complete/valid patches
        assert found_patches == ["456-valid"]

    def test_list_all_patches_permission_error(self, patch_directory):
        """Test handling permission errors when listing patches."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory
        patch_path = schema_patches_dir / "456-test"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        
        # Make directory unreadable
        patch_path.chmod(0o000)
        
        try:
            found_patches = patch_dir.list_all_patches()
            
            # Should handle permission error gracefully
            # Might return empty list or exclude unreadable patches
            assert isinstance(found_patches, list)
            
        finally:
            # Restore permissions for cleanup
            patch_path.chmod(0o755)


class TestDeletePatchDirectory:
    """Test patch directory deletion."""

    def test_delete_patch_directory_without_confirm(self, patch_directory):
        """Test deletion without confirmation flag."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory
        patch_path = schema_patches_dir / "456-user-auth"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        
        result = patch_dir.delete_patch_directory("456-user-auth")
        
        # Should return False and not delete
        assert result is False
        assert patch_path.exists()

    def test_delete_patch_directory_confirm_false_explicit(self, patch_directory):
        """Test deletion with explicit confirm=False."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory
        patch_path = schema_patches_dir / "456-user-auth"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        
        result = patch_dir.delete_patch_directory("456-user-auth", confirm=False)
        
        # Should return False and not delete
        assert result is False
        assert patch_path.exists()

    def test_delete_patch_directory_with_confirm(self, patch_directory):
        """Test deletion with confirmation flag."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory with files
        patch_path = schema_patches_dir / "456-user-auth"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        (patch_path / "01_test.sql").write_text("SELECT 1;")
        
        result = patch_dir.delete_patch_directory("456-user-auth", confirm=True)
        
        # Should return True and delete directory
        assert result is True
        assert not patch_path.exists()

    def test_delete_patch_directory_with_subdirectories(self, patch_directory):
        """Test deletion of patch directory with subdirectories."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory with subdirectory
        patch_path = schema_patches_dir / "456-complex"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        
        # Create subdirectory with files
        sub_dir = patch_path / "scripts"
        sub_dir.mkdir()
        (sub_dir / "helper.sql").write_text("-- Helper script")
        
        result = patch_dir.delete_patch_directory("456-complex", confirm=True)
        
        # Should delete entire directory tree
        assert result is True
        assert not patch_path.exists()
        assert not sub_dir.exists()

    def test_delete_patch_directory_nonexistent(self, patch_directory):
        """Test deleting nonexistent patch directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        with pytest.raises(PatchDirectoryError, match="Patch directory does not exist"):
            patch_dir.delete_patch_directory("999-nonexistent", confirm=True)

    def test_delete_patch_directory_is_file_not_directory(self, patch_directory):
        """Test deleting when patch 'directory' is actually a file."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create file instead of directory
        patch_file = schema_patches_dir / "456-user-auth"
        patch_file.write_text("This is a file, not a directory")
        
        with pytest.raises(PatchDirectoryError, match="not a directory"):
            patch_dir.delete_patch_directory("456-user-auth", confirm=True)

    def test_delete_patch_directory_permission_error(self, patch_directory):
        """Test deletion with permission error."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory
        patch_path = schema_patches_dir / "456-user-auth"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Test")
        
        # Make parent directory read-only to prevent deletion
        schema_patches_dir.chmod(0o444)
        
        try:
            with pytest.raises(PatchDirectoryError, match="Permission denied"):
                patch_dir.delete_patch_directory("456-user-auth", confirm=True)
        finally:
            # Restore permissions for cleanup
            schema_patches_dir.chmod(0o755)

    def test_delete_patch_directory_readonly_files(self, patch_directory):
        """Test deletion of patch directory with read-only files."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory with read-only file
        patch_path = schema_patches_dir / "456-readonly"
        patch_path.mkdir()
        
        readonly_file = patch_path / "readonly.sql"
        readonly_file.write_text("SELECT 1;")
        readonly_file.chmod(0o444)  # Make file read-only
        
        try:
            result = patch_dir.delete_patch_directory("456-readonly", confirm=True)
            
            # Should force delete read-only files
            assert result is True
            assert not patch_path.exists()
            
        except PatchDirectoryError:
            # If deletion fails due to read-only files, that's also valid behavior
            # depending on implementation
            pass
        finally:
            # Cleanup if deletion failed
            if patch_path.exists():
                readonly_file.chmod(0o755)

    def test_delete_patch_directory_empty_directory(self, patch_directory):
        """Test deletion of empty patch directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create empty patch directory
        patch_path = schema_patches_dir / "456-empty"
        patch_path.mkdir()
        
        result = patch_dir.delete_patch_directory("456-empty", confirm=True)
        
        # Should successfully delete empty directory
        assert result is True
        assert not patch_path.exists()

    def test_delete_patch_directory_validates_patch_id(self, patch_directory):
        """Test that deletion validates patch ID format."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Should validate patch ID before attempting deletion
        with pytest.raises(PatchDirectoryError, match="Invalid patch ID"):
            patch_dir.delete_patch_directory("invalid@patch", confirm=True)

    def test_delete_patch_directory_safety_check(self, patch_directory):
        """Test safety checks prevent accidental deletion."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patch directory
        patch_path = schema_patches_dir / "456-important"
        patch_path.mkdir()
        (patch_path / "README.md").write_text("# Important patch")
        (patch_path / "01_critical.sql").write_text("-- Critical changes")
        
        # Multiple calls without confirm should always return False
        for _ in range(3):
            result = patch_dir.delete_patch_directory("456-important")
            assert result is False
            assert patch_path.exists()
        
        # Only confirm=True should actually delete
        result = patch_dir.delete_patch_directory("456-important", confirm=True)
        assert result is True
        assert not patch_path.exists()


class TestUtilitieIntegration:
    """Test integration between utility methods."""

    def test_path_and_list_integration(self, patch_directory):
        """Test integration between get_patch_directory_path and list_all_patches."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create some patches
        patch_ids = ["123-first", "456-second", "789-third"]
        for patch_id in patch_ids:
            patch_path = patch_dir.get_patch_directory_path(patch_id)
            patch_path.mkdir()
            (patch_path / "README.md").write_text(f"# {patch_id}")
        
        # List should find all created patches
        found_patches = patch_dir.list_all_patches()
        assert set(found_patches) == set(patch_ids)
        
        # Each found patch should have valid path
        for patch_id in found_patches:
            path = patch_dir.get_patch_directory_path(patch_id)
            assert path.exists()
            assert path.is_dir()

    def test_list_and_delete_integration(self, patch_directory):
        """Test integration between list_all_patches and delete_patch_directory."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Create patches
        patch_ids = ["111-delete-me", "222-keep-me", "333-delete-me-too"]
        for patch_id in patch_ids:
            patch_path = schema_patches_dir / patch_id
            patch_path.mkdir()
            (patch_path / "README.md").write_text(f"# {patch_id}")
        
        # Verify all patches exist
        found_patches = patch_dir.list_all_patches()
        assert len(found_patches) == 3
        
        # Delete some patches
        assert patch_dir.delete_patch_directory("111-delete-me", confirm=True) is True
        assert patch_dir.delete_patch_directory("333-delete-me-too", confirm=True) is True
        
        # List should now show only remaining patch
        remaining_patches = patch_dir.list_all_patches()
        assert remaining_patches == ["222-keep-me"]

    def test_path_normalization_consistency(self, patch_directory):
        """Test that path methods handle normalization consistently."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        # Test various forms of the same patch ID
        patch_id_variants = [
            "456-user-auth",
            " 456-user-auth ",
            "456-user-auth\n",
            "456-user-auth\t"
        ]
        
        # All variants should produce same path
        paths = [patch_dir.get_patch_directory_path(pid) for pid in patch_id_variants]
        normalized_paths = [p.resolve() for p in paths]
        
        # All normalized paths should be identical
        assert len(set(str(p) for p in normalized_paths)) == 1

    def test_error_consistency_across_methods(self, patch_directory):
        """Test that error handling is consistent across utility methods."""
        patch_dir, repo, temp_dir, schema_patches_dir = patch_directory
        
        invalid_patch_ids = ["", "invalid@patch", "../../../etc", None]
        
        for invalid_id in invalid_patch_ids:
            if invalid_id is None:
                continue
                
            # Methods should raise similar errors for invalid IDs
            try:
                patch_dir.get_patch_directory_path(invalid_id)
            except Exception as e1:
                try:
                    patch_dir.delete_patch_directory(invalid_id, confirm=True)
                except Exception as e2:
                    # Error types should be consistent
                    assert type(e1) == type(e2) or issubclass(type(e1), PatchDirectoryError)
