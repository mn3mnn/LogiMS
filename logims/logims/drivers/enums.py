from enum import Enum

class DriverDocumentsStatus(str, Enum):
    MISSING = "missing"
    EXPIRED = "expired"
    VALID = "valid"

