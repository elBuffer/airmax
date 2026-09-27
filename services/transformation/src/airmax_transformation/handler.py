from datetime import UTC, datetime

from airmax_transformation.application.refresh_air_quality import refresh_air_quality
from airmax_transformation.config import Settings
from airmax_transformation.pipeline import REFERENCE

__all__ = ["REFERENCE", "lambda_handler"]


def _configured_store(settings):
    if settings.store == "local":
        from .adapters.local_store import LocalStore

        return LocalStore(settings.local_root)

    from .adapters.s3_store import S3Store

    return S3Store(settings.raw_bucket, settings.results_bucket)


def lambda_handler(_event=None, _context=None, store=None, now=None):
    settings = Settings()
    result_store = store if store is not None else _configured_store(settings)
    generated_at = (now or datetime.now(UTC)).astimezone(UTC)
    return refresh_air_quality(result_store, generated_at)
