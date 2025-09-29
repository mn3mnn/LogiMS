import os
import uuid

def driver_document_path(instance, filename):
    original_name = filename.split('.')[0]
    ext = filename.split('.')[-1]
    random_name = f"{original_name}-{uuid.uuid4().hex[:12]}.{ext}"
    return os.path.join(
        "driver_documents",
        instance.__class__.__name__.lower(),
        random_name
    )
