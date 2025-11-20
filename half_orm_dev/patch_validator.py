"""
Patch ID validation and normalization for half-orm-dev.

This module provides validation and normalization of patch identifiers
used in the patch-centric workflow.
"""

import re
import unicodedata
from typing import Optional
from dataclasses import dataclass


class InvalidPatchIdError(Exception):
    """Raised when patch ID format is invalid."""
    pass


class DuplicatePatchIdError(Exception):
    """Raised when patch ID already exists."""
    pass


@dataclass
class PatchInfo:
    """Information about a validated patch ID."""
    original_id: str
    normalized_id: str
    ticket_number: Optional[str]
    description: Optional[str]
    is_numeric_only: bool


class PatchValidator:
    """
    Validates and normalizes patch IDs for the patch-centric workflow.

    Handles both formats:
    - Numeric only: "456" -> generates description if possible
    - Full format: "456-user-authentication" -> validates format

    Examples:
        validator = PatchValidator()

        # Numeric patch ID
        info = validator.validate_patch_id("456")
        # Returns: PatchInfo(original_id="456", normalized_id="456", ...)

        # Full patch ID
        info = validator.validate_patch_id("456-user-authentication")
        # Returns: PatchInfo(original_id="456-user-authentication",
        #                   normalized_id="456-user-authentication", ...)

        # Invalid format raises exception
        try:
            validator.validate_patch_id("invalid@patch")
        except InvalidPatchIdError as e:
            print(f"Invalid patch ID: {e}")
    """

    # Regex patterns for validation
    NUMERIC_PATTERN = re.compile(r'^\d+$')
    FULL_PATTERN = re.compile(r'^\d+-[a-z0-9]+(?:-[a-z0-9]+)*$')
    DESCRIPTION_PATTERN = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

    def __init__(self):
        """Initialize patch validator."""
        pass

    def validate_patch_id(self, patch_id: str) -> PatchInfo:
        """
        Validate and parse a patch ID.

        Args:
            patch_id: The patch identifier to validate

        Returns:
            PatchInfo object with parsed information

        Raises:
            InvalidPatchIdError: If patch ID format is invalid

        Examples:
            # Numeric ID
            info = validator.validate_patch_id("456")
            assert info.ticket_number == "456"
            assert info.is_numeric_only == True

            # Full ID
            info = validator.validate_patch_id("456-user-auth")
            assert info.ticket_number == "456"
            assert info.description == "user-auth"
            assert info.is_numeric_only == False
        """
        if not patch_id or not patch_id.strip():
            raise InvalidPatchIdError("Patch ID cannot be empty")

        patch_id = patch_id.strip().lstrip('0') or '0'

        # Check for numeric-only format
        if self.NUMERIC_PATTERN.match(patch_id):
            return PatchInfo(
                original_id=patch_id,
                normalized_id=patch_id,
                ticket_number=int(patch_id),
                description=None,
                is_numeric_only=True
            )

        # Check for full format (number-description)
        if self.FULL_PATTERN.match(patch_id):
            parts = patch_id.split('-', 1)
            ticket_number = int(parts[0])
            description = parts[1]

            return PatchInfo(
                original_id=patch_id,
                normalized_id=patch_id,
                ticket_number=ticket_number,
                description=description,
                is_numeric_only=False
            )

        # If we get here, format is invalid
        if not patch_id[0].isdigit():
            raise InvalidPatchIdError("Patch ID must start with a ticket number")
        else:
            raise InvalidPatchIdError(
                f"Invalid patch ID format: '{patch_id}'. "
                f"Expected formats: '123' or '123-description' (lowercase, hyphens only)"
            )

    def normalize_patch_id(self, patch_id: str, suggested_description: Optional[str] = None) -> str:
        """
        Normalize a patch ID to the standard format.

        For numeric IDs, tries to generate a meaningful description.
        For full IDs, validates format and returns as-is.

        Args:
            patch_id: The patch identifier to normalize
            suggested_description: Optional description to use for numeric IDs

        Returns:
            Normalized patch ID in format "number-description"

        Raises:
            InvalidPatchIdError: If patch ID format is invalid

        Examples:
            # Numeric with suggestion
            result = validator.normalize_patch_id("456", "user-authentication")
            assert result == "456-user-authentication"

            # Numeric without suggestion (uses fallback)
            result = validator.normalize_patch_id("456")
            assert result == "456"  # or "456-feature" based on context

            # Already normalized
            result = validator.normalize_patch_id("456-existing")
            assert result == "456-existing"
        """
        # First validate the input format
        patch_info = self.validate_patch_id(patch_id)

        # If it's already in full format, return as-is
        if not patch_info.is_numeric_only:
            return patch_info.normalized_id

        # For numeric-only IDs, we need to add a description
        if suggested_description:
            # Sanitize the suggested description
            clean_description = self.sanitize_description(suggested_description)
            return f"{patch_info.ticket_number}-{clean_description}"
        else:
            # Use fallback description
            fallback_description = self.generate_fallback_description(patch_info.ticket_number)
            return f"{patch_info.ticket_number}-{fallback_description}"

    def extract_ticket_number(self, patch_id: str) -> Optional[str]:
        """
        Extract ticket number from patch ID.

        Args:
            patch_id: The patch identifier

        Returns:
            Ticket number if found, None otherwise

        Examples:
            assert validator.extract_ticket_number("456-auth") == "456"
            assert validator.extract_ticket_number("456") == "456"
            assert validator.extract_ticket_number("invalid") is None
        """
        if not patch_id or not patch_id.strip():
            return None

        patch_id = patch_id.strip()

        # Check numeric-only format
        if self.NUMERIC_PATTERN.match(patch_id):
            return patch_id

        # Check full format and extract number part
        if self.FULL_PATTERN.match(patch_id):
            return patch_id.split('-', 1)[0]

        # Invalid format
        return None

    def extract_description(self, patch_id: str) -> Optional[str]:
        """
        Extract description part from patch ID.

        Args:
            patch_id: The patch identifier

        Returns:
            Description if found, None for numeric-only IDs

        Examples:
            assert validator.extract_description("456-user-auth") == "user-auth"
            assert validator.extract_description("456") is None
        """
        if not patch_id or not patch_id.strip():
            return None

        patch_id = patch_id.strip()

        # Numeric-only format has no description
        if self.NUMERIC_PATTERN.match(patch_id):
            return None

        # Extract description from full format
        if self.FULL_PATTERN.match(patch_id):
            parts = patch_id.split('-', 1)
            return parts[1]  # Return everything after first hyphen

        # Invalid format
        return None

    def is_valid_description(self, description: str) -> bool:
        """
        Check if description part follows naming conventions.

        Args:
            description: Description to validate

        Returns:
            True if description is valid, False otherwise

        Examples:
            assert validator.is_valid_description("user-authentication") == True
            assert validator.is_valid_description("user_auth") == False  # no underscores
            assert validator.is_valid_description("UserAuth") == False   # no uppercase
        """
        if not description:
            return False

        # Use the DESCRIPTION_PATTERN regex to validate format
        return bool(self.DESCRIPTION_PATTERN.match(description))

    def generate_fallback_description(self, ticket_number: str) -> str:
        """
        Generate a fallback description for numeric patch IDs.

        Returns a simple default description. Developers should provide
        meaningful descriptions themselves for better clarity.

        Args:
            ticket_number: The numeric ticket identifier

        Returns:
            Default description "patch"

        Examples:
            desc = validator.generate_fallback_description("456")
            assert desc == "patch"
        """
        return "patch"

    def sanitize_description(self, description: str) -> str:
        """
        Sanitize a description to follow naming conventions.

        - Convert to lowercase
        - Replace spaces/underscores with hyphens
        - Remove invalid characters
        - Truncate if too long

        Args:
            description: Raw description to sanitize

        Returns:
            Sanitized description following conventions

        Examples:
            assert validator.sanitize_description("User Authentication") == "user-authentication"
            assert validator.sanitize_description("user_auth_system") == "user-auth-system"
            assert validator.sanitize_description("Fix Bug #123") == "fix-bug-123"
        """
        if not description:
            return "patch"

        # Convert to lowercase
        result = description.lower()

        # Remove accents (transliteration)
        result = unicodedata.normalize('NFD', result)
        result = ''.join(c for c in result if unicodedata.category(c) != 'Mn')

        # Replace spaces and underscores with hyphens
        result = re.sub(r'[\s_]+', '-', result)

        # Replace other separators (dots, @, etc.) with hyphens before removing them
        result = re.sub(r'[^\w\-]', '-', result)

        # Now remove invalid characters (keep only letters, numbers, hyphens)
        result = re.sub(r'[^a-z0-9\-]', '', result)

        # Clean up multiple consecutive hyphens
        result = re.sub(r'-+', '-', result)

        # Remove leading and trailing hyphens
        result = result.strip('-')

        # If result is empty after cleaning, use fallback
        if not result:
            return "patch"

        # Truncate if too long (reasonable limit)
        if len(result) > 50:
            result = result[:50].rstrip('-')

        return result
