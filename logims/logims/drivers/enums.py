from enum import Enum

class DriverDocumentsStatus(str, Enum):
    MISSING_DOCS = "missing_docs"
    EXPIRED_DOCS = "expired_docs"

