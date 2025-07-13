#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TemporaryKey class for SchemaPatches module

Provides temporary key management with tempX format (temp1, temp2, temp3, ...)
for parallel development without conflicts between developers.

Key Features:
- Unlimited temporary key range (temp1 to tempN, no arbitrary limits)
- Format validation (tempX where X is positive integer)
- Numeric extraction and comparison for sorting
- Type-safe creation and validation

Usage:
    >>> key = TemporaryKey("temp42")
    >>> key.get_number()  # 42
    >>> TemporaryKey.from_number(1)  # TemporaryKey("temp1")
    >>> key1 < key2  # Numeric comparison
"""

from dataclasses import dataclass
from typing import Union
from .exceptions import TemporaryKeyError, validate_temporary_key_format


@dataclass
class TemporaryKey:
    """
    Representation of a temporary key for patch identification.
    
    Temporary keys use tempX format (temp1, temp2, temp3, ...) allowing
    unlimited parallel development without conflicts between developers.
    
    Attributes:
        key (str): The temporary key string (e.g., 'temp1', 'temp42', 'temp999')
    """
    key: str
    
    def __post_init__(self):
        """Validate temporary key format after initialization."""
        if not self.is_valid_temporary_key(self.key):
            raise TemporaryKeyError(f"Invalid temporary key format: '{self.key}'", temp_key=self.key)
    
    @staticmethod
    def is_valid_temporary_key(key: str) -> bool:
        """
        Validate temporary key format.
        
        Valid format: tempX where X is a positive integer (temp1, temp2, temp999, etc.)
        No arbitrary limit on the number to support unlimited parallel development.
        
        Args:
            key (str): Key to validate
            
        Returns:
            bool: True if valid format, False otherwise
            
        Example:
            >>> TemporaryKey.is_valid_temporary_key("temp1")     # True
            >>> TemporaryKey.is_valid_temporary_key("temp42")    # True
            >>> TemporaryKey.is_valid_temporary_key("temp999")   # True
            >>> TemporaryKey.is_valid_temporary_key("temp0")     # False (zero not allowed)
            >>> TemporaryKey.is_valid_temporary_key("tempX")     # False (not numeric)
            >>> TemporaryKey.is_valid_temporary_key("A")         # False (old format)
        """
        pass
    
    def get_number(self) -> int:
        """
        Extract the numeric part of the temporary key.
        
        Returns:
            int: Numeric part of temporary key
            
        Raises:
            TemporaryKeyError: If key format is invalid
            
        Example:
            >>> TemporaryKey("temp42").get_number()  # 42
            >>> TemporaryKey("temp1").get_number()   # 1
        """
        pass
    
    @classmethod
    def from_number(cls, number: int) -> 'TemporaryKey':
        """
        Create temporary key from number.
        
        Args:
            number (int): Positive integer for temporary key
            
        Returns:
            TemporaryKey: Corresponding temporary key
            
        Raises:
            TemporaryKeyError: If number is invalid (zero or negative)
            
        Example:
            >>> TemporaryKey.from_number(1)   # TemporaryKey("temp1")
            >>> TemporaryKey.from_number(42)  # TemporaryKey("temp42")
        """
        pass
    
    @classmethod
    def parse(cls, key_input: Union[str, int]) -> 'TemporaryKey':
        """
        Parse temporary key from string or integer input.
        
        Flexible constructor that accepts both string format ("temp1") 
        and integer format (1) for convenience.
        
        Args:
            key_input (Union[str, int]): String key or integer number
            
        Returns:
            TemporaryKey: Parsed temporary key
            
        Raises:
            TemporaryKeyError: If input format is invalid
            
        Example:
            >>> TemporaryKey.parse("temp1")  # TemporaryKey("temp1")
            >>> TemporaryKey.parse(1)        # TemporaryKey("temp1")
            >>> TemporaryKey.parse("invalid")  # Raises TemporaryKeyError
        """
        pass
    
    def increment(self) -> 'TemporaryKey':
        """
        Create next temporary key by incrementing number.
        
        Returns:
            TemporaryKey: Next temporary key (temp1 → temp2, temp42 → temp43)
            
        Example:
            >>> TemporaryKey("temp1").increment()   # TemporaryKey("temp2")
            >>> TemporaryKey("temp42").increment()  # TemporaryKey("temp43")
        """
        pass
    
    def decrement(self) -> 'TemporaryKey':
        """
        Create previous temporary key by decrementing number.
        
        Returns:
            TemporaryKey: Previous temporary key (temp2 → temp1, temp43 → temp42)
            
        Raises:
            TemporaryKeyError: If decrementing would result in temp0 or negative
            
        Example:
            >>> TemporaryKey("temp2").decrement()   # TemporaryKey("temp1")
            >>> TemporaryKey("temp1").decrement()   # Raises TemporaryKeyError
        """
        pass
    
    def __lt__(self, other: 'TemporaryKey') -> bool:
        """
        Enable sorting of temporary keys by numeric value.
        
        Args:
            other (TemporaryKey): Other temporary key to compare
            
        Returns:
            bool: True if this key's number is less than other's
            
        Example:
            >>> temp1 = TemporaryKey("temp1")
            >>> temp2 = TemporaryKey("temp2")
            >>> temp1 < temp2  # True
            >>> temp2 < temp1  # False
        """
        pass
    
    def __le__(self, other: 'TemporaryKey') -> bool:
        """Less than or equal comparison."""
        pass
    
    def __gt__(self, other: 'TemporaryKey') -> bool:
        """Greater than comparison."""
        pass
    
    def __ge__(self, other: 'TemporaryKey') -> bool:
        """Greater than or equal comparison."""
        pass
    
    def __eq__(self, other: object) -> bool:
        """
        Equality comparison.
        
        Args:
            other (object): Object to compare with
            
        Returns:
            bool: True if both are TemporaryKey with same key string
        """
        pass
    
    def __hash__(self) -> int:
        """Hash function for use in sets and dictionaries."""
        pass
    
    def __str__(self) -> str:
        """
        String representation of temporary key.
        
        Returns:
            str: The key string (e.g., "temp1", "temp42")
        """
        pass
    
    def __repr__(self) -> str:
        """
        Detailed representation for debugging.
        
        Returns:
            str: Detailed representation including class name
            
        Example:
            >>> repr(TemporaryKey("temp1"))  # "TemporaryKey('temp1')"
        """
        pass
