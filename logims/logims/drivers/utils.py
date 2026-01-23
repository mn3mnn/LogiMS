import os
import uuid
from rest_framework import serializers


def driver_document_path(instance, filename):
    original_name = filename.split('.')[0]
    ext = filename.split('.')[-1]
    random_name = f"{original_name}-{uuid.uuid4().hex[:12]}.{ext}"
    return os.path.join(
        "driver_documents",
        instance.__class__.__name__.lower(),
        random_name
    )


def validate_phone_number(value):
    """
    Single Source of Truth (SSOT) for phone number validation.
    
    Validates phone number format:
    - Only digits allowed (with optional '+' prefix)
    - 7-15 digits required (after removing '+' if present)
    - Whitespace is trimmed
    
    Args:
        value: The phone number string to validate
        
    Returns:
        str: The cleaned phone number (with + if it was there)
        
    Raises:
        serializers.ValidationError: If the phone number format is invalid
    """
    if not value:
        return value
    
    # Remove whitespace
    phone = value.strip()
    
    # Check if it starts with + and remove it for validation
    if phone.startswith('+'):
        digits = phone[1:]
    else:
        digits = phone
    
    # Check if all remaining characters are digits
    if not digits.isdigit():
        raise serializers.ValidationError(
            "Phone number must contain only digits with an optional '+' prefix."
        )
    
    # Check length (7-15 digits after removing +)
    if len(digits) < 7 or len(digits) > 15:
        raise serializers.ValidationError(
            "Phone number must have 7-15 digits (after removing '+' if present)."
        )
    
    # Return the cleaned phone number (with + if it was there)
    return phone
