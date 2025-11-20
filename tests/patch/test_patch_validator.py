"""
Comprehensive unit tests for PatchValidator.

Tests all methods including edge cases and error handling.
All tests should fail until PatchValidator methods are implemented.
"""

import pytest
from unittest.mock import Mock, patch
from half_orm_dev.patch_validator import (
    PatchValidator,
    PatchInfo,
    InvalidPatchIdError,
    DuplicatePatchIdError
)


class TestPatchValidator:
    """Test suite for PatchValidator class."""

    @pytest.fixture
    def validator(self):
        """Fixture providing a PatchValidator instance."""
        return PatchValidator()

    # Tests for validate_patch_id method

    def test_validate_patch_id_numeric_only(self, validator):
        """Test validation of numeric-only patch IDs."""
        result = validator.validate_patch_id("456")

        assert isinstance(result, PatchInfo)
        assert result.original_id == "456"
        assert result.normalized_id == "456"
        assert result.ticket_number == 456
        assert result.description is None
        assert result.is_numeric_only is True

    def test_validate_patch_id_full_format(self, validator):
        """Test validation of full format patch IDs with various description lengths."""
        # Simple description
        result = validator.validate_patch_id("456-user-authentication")
        assert isinstance(result, PatchInfo)
        assert result.original_id == "456-user-authentication"
        assert result.normalized_id == "456-user-authentication"
        assert result.ticket_number == 456
        assert result.description == "user-authentication"
        assert result.is_numeric_only is False

        # Multi-part description
        result = validator.validate_patch_id("789-user-auth-system-fix")
        assert result.ticket_number == 789
        assert result.description == "user-auth-system-fix"
        assert result.is_numeric_only is False

    def test_validate_patch_id_invalid_format_empty(self, validator):
        """Test validation with empty patch ID."""
        with pytest.raises(InvalidPatchIdError, match="Patch ID cannot be empty"):
            validator.validate_patch_id("")

    def test_validate_patch_id_invalid_format_special_chars(self, validator):
        """Test validation with invalid characters."""
        invalid_ids = [
            "456@invalid",
            "456_underscore",
            "456-Invalid-Case",
            "456-with space",
            "456-with.dot",
            "not-numeric-start"
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(InvalidPatchIdError):
                validator.validate_patch_id(invalid_id)

    def test_validate_patch_id_invalid_format_no_number(self, validator):
        """Test validation with non-numeric start."""
        with pytest.raises(InvalidPatchIdError, match="Patch ID must start with a ticket number"):
            validator.validate_patch_id("feature-without-number")

    # Tests for normalize_patch_id method

    def test_normalize_patch_id_numeric_with_suggestion(self, validator):
        """Test normalization of numeric ID with suggested description."""
        result = validator.normalize_patch_id("456", "user-authentication")
        assert result == "456-user-authentication"

    def test_normalize_patch_id_numeric_without_suggestion(self, validator):
        """Test normalization of numeric ID without suggestion (uses fallback)."""
        with patch.object(validator, 'generate_fallback_description', return_value="feature"):
            result = validator.normalize_patch_id("456")
            assert result == "456-feature"

    def test_normalize_patch_id_already_normalized(self, validator):
        """Test normalization of already valid full format."""
        result = validator.normalize_patch_id("456-existing-patch")
        assert result == "456-existing-patch"

    def test_normalize_patch_id_sanitize_suggestion(self, validator):
        """Test normalization sanitizes suggested descriptions."""
        with patch.object(validator, 'sanitize_description', return_value="user-auth"):
            result = validator.normalize_patch_id("456", "User Authentication")
            assert result == "456-user-auth"

    def test_normalize_patch_id_invalid_input(self, validator):
        """Test normalization with invalid patch ID."""
        with pytest.raises(InvalidPatchIdError):
            validator.normalize_patch_id("invalid@patch")

    # Tests for extract_ticket_number method

    def test_extract_ticket_number_numeric_only(self, validator):
        """Test ticket number extraction from numeric ID."""
        assert validator.extract_ticket_number("456") == "456"

    def test_extract_ticket_number_full_format(self, validator):
        """Test ticket number extraction from full format."""
        assert validator.extract_ticket_number("789-user-auth") == "789"

    def test_extract_ticket_number_invalid_format(self, validator):
        """Test ticket number extraction from invalid format."""
        assert validator.extract_ticket_number("invalid-format") is None
        assert validator.extract_ticket_number("") is None
        assert validator.extract_ticket_number("no-numbers-here") is None

    # Tests for extract_description method

    def test_extract_description_full_format(self, validator):
        """Test description extraction from full format."""
        assert validator.extract_description("456-user-authentication") == "user-authentication"

    def test_extract_description_complex_description(self, validator):
        """Test description extraction with multiple parts."""
        assert validator.extract_description("789-auth-system-bugfix") == "auth-system-bugfix"

    def test_extract_description_numeric_only(self, validator):
        """Test description extraction from numeric-only ID."""
        assert validator.extract_description("456") is None

    def test_extract_description_invalid_format(self, validator):
        """Test description extraction from invalid format."""
        assert validator.extract_description("invalid-format") is None
        assert validator.extract_description("") is None

    # Tests for is_valid_description method

    def test_is_valid_description_valid_cases(self, validator):
        """Test description validation with valid cases."""
        valid_descriptions = [
            "user-authentication",
            "auth",
            "user-auth-system",
            "bugfix",
            "feature-123",
            "a",  # single character
            "very-long-description-with-many-parts"
        ]

        for desc in valid_descriptions:
            assert validator.is_valid_description(desc) is True, f"'{desc}' should be valid"

    def test_is_valid_description_invalid_cases(self, validator):
        """Test description validation with invalid cases."""
        invalid_descriptions = [
            "User-Auth",          # uppercase
            "user_auth",          # underscore
            "user auth",          # space
            "user.auth",          # dot
            "user@auth",          # special char
            "",                   # empty
            "-leading-dash",      # starts with dash
            "trailing-dash-",     # ends with dash
            "double--dash",       # double dash
        ]

        for desc in invalid_descriptions:
            assert validator.is_valid_description(desc) is False, f"'{desc}' should be invalid"

    # Tests for generate_fallback_description method

    def test_generate_fallback_description_default(self, validator):
        """Test fallback description generation returns 'patch'."""
        result = validator.generate_fallback_description("456")
        assert result == "patch"
        assert validator.is_valid_description(result)

    def test_generate_fallback_description_any_ticket_number(self, validator):
        """Test fallback description is consistent for any ticket number."""
        test_numbers = ["1", "123", "999999", "42"]
        for ticket_num in test_numbers:
            result = validator.generate_fallback_description(ticket_num)
            assert result == "patch"
            assert validator.is_valid_description(result)

    # Tests for sanitize_description method

    def test_sanitize_description_spaces_to_hyphens(self, validator):
        """Test sanitization converts spaces to hyphens."""
        assert validator.sanitize_description("User Authentication") == "user-authentication"

    def test_sanitize_description_underscores_to_hyphens(self, validator):
        """Test sanitization converts underscores to hyphens."""
        assert validator.sanitize_description("user_auth_system") == "user-auth-system"

    def test_sanitize_description_uppercase_to_lowercase(self, validator):
        """Test sanitization converts uppercase to lowercase."""
        assert validator.sanitize_description("UserAuthSystem") == "userauthsystem"
        assert validator.sanitize_description("USER-AUTH") == "user-auth"

    def test_sanitize_description_remove_special_chars(self, validator):
        """Test sanitization removes invalid characters."""
        assert validator.sanitize_description("Fix Bug #123!") == "fix-bug-123"

    def test_sanitize_description_normalize_accents(self, validator):
        """Test sanitization normalize accents."""
        assert validator.sanitize_description("joël@auth.com") == "joel-auth-com"
        assert validator.sanitize_description("éçèà") == "ecea"

    def test_sanitize_description_clean_multiple_hyphens(self, validator):
        """Test sanitization cleans up multiple consecutive hyphens."""
        assert validator.sanitize_description("user--auth") == "user-auth"
        assert validator.sanitize_description("user---system") == "user-system"

    def test_sanitize_description_trim_hyphens(self, validator):
        """Test sanitization trims leading/trailing hyphens."""
        assert validator.sanitize_description("-user-auth-") == "user-auth"
        assert validator.sanitize_description("--user--") == "user"

    def test_sanitize_description_truncate_long(self, validator):
        """Test sanitization truncates very long descriptions."""
        long_desc = "very-long-description-that-exceeds-reasonable-length-limits-and-should-be-truncated"
        result = validator.sanitize_description(long_desc)
        assert len(result) <= 50  # reasonable limit
        assert not result.endswith("-")  # no trailing dash after truncation

    def test_sanitize_description_empty_result(self, validator):
        """Test sanitization with input that becomes empty."""
        result = validator.sanitize_description("@#$%^&*()")
        assert result == "patch"  # fallback for empty result


class TestPatchValidatorIntegration:
    """Integration tests for PatchValidator workflows."""

    @pytest.fixture
    def validator(self):
        """Fixture providing a PatchValidator instance."""
        return PatchValidator()

    def test_complete_workflow_numeric_id(self, validator):
        """Test complete validation workflow for numeric ID."""
        # Validate
        info = validator.validate_patch_id("456")
        assert info.is_numeric_only is True

        # Normalize with context
        normalized = validator.normalize_patch_id("456", "user-authentication")
        assert normalized == "456-user-authentication"

        # Extract components
        assert validator.extract_ticket_number(normalized) == "456"
        assert validator.extract_description(normalized) == "user-authentication"

    def test_complete_workflow_full_id(self, validator):
        """Test complete validation workflow for full format ID."""
        patch_id = "789-security-fix"

        # Validate
        info = validator.validate_patch_id(patch_id)
        assert info.is_numeric_only is False
        assert info.ticket_number == 789
        assert info.description == "security-fix"

        # Normalize (should return unchanged)
        normalized = validator.normalize_patch_id(patch_id)
        assert normalized == patch_id

    def test_error_handling_chain(self, validator):
        """Test error propagation through method chain."""
        invalid_id = "invalid@format"

        # Should fail at validation
        with pytest.raises(InvalidPatchIdError):
            validator.validate_patch_id(invalid_id)

        # Should fail at normalization
        with pytest.raises(InvalidPatchIdError):
            validator.normalize_patch_id(invalid_id)

        # Extract methods should handle gracefully
        assert validator.extract_ticket_number(invalid_id) is None
        assert validator.extract_description(invalid_id) is None


class TestPatchValidatorEdgeCases:
    """Edge case tests for PatchValidator."""

    @pytest.fixture
    def validator(self):
        """Fixture providing a PatchValidator instance."""
        return PatchValidator()

    def test_very_large_ticket_numbers(self, validator):
        """Test handling of very large ticket numbers."""
        large_number = "999999999"
        result = validator.validate_patch_id(large_number)
        assert result.ticket_number == int(large_number)

    def test_single_character_description(self, validator):
        """Test handling of single character descriptions."""
        result = validator.validate_patch_id("456-a")
        assert result.description == "a"


    def test_zeor_ticket_number(self, validator):
        """Test handling of very large ticket numbers."""
        zero = "000"
        result = validator.validate_patch_id(zero)
        assert result.ticket_number == int(zero)

