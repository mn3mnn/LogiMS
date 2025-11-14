from storages.backends.s3 import S3Storage


class R2MediaStorage(S3Storage):
    """
    Storage backend for files that should live in Cloudflare R2 only.

    Uses the global AWS_* / R2_* settings configured in the environment.
    We do NOT set a custom location here because each FileField's upload_to
    controls the sub-path (e.g. driver_documents/, file_uploads/).
    """

    default_acl = None
    file_overwrite = False


