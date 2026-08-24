"""阿里云 OSS 对象存储（Python SDK V2）。"""
from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

from base.logger import logger

_client = None


def is_enabled() -> bool:
    from backend.app.core.config import settings

    return bool(settings.OSS_ENABLED and settings.OSS_BUCKET and settings.OSS_REGION)


def _get_client():
    global _client
    if _client is not None:
        return _client

    import alibabacloud_oss_v2 as oss

    from backend.app.core.config import settings

    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    cfg.region = settings.OSS_REGION
    if settings.OSS_ENDPOINT:
        cfg.endpoint = settings.OSS_ENDPOINT

    _client = oss.Client(cfg)
    return _client


def build_object_key(knowledge_base_id: int, file_name: str) -> str:
    from backend.app.core.config import settings

    safe_name = Path(file_name).name.replace(" ", "_")
    prefix = (settings.OSS_PREFIX or "devmind-ai").strip("/")
    return f"{prefix}/kb/{knowledge_base_id}/{uuid.uuid4().hex}_{safe_name}"


def create_presigned_put_url(object_key: str, content_type: str | None = None) -> dict:
    """生成浏览器直传用的预签名 PUT URL。"""
    import alibabacloud_oss_v2 as oss

    from backend.app.core.config import settings

    client = _get_client()
    request = oss.PutObjectRequest(
        bucket=settings.OSS_BUCKET,
        key=object_key,
    )
    if content_type:
        request.content_type = content_type

    pre_result = client.presign(
        request,
        expires=timedelta(seconds=settings.OSS_PRESIGN_EXPIRES),
    )
    headers = {str(k): str(v) for k, v in (pre_result.signed_headers or {}).items()}
    return {
        "method": pre_result.method,
        "url": pre_result.url,
        "headers": headers,
        "expiresAt": pre_result.expiration.isoformat() if pre_result.expiration else None,
        "bucket": settings.OSS_BUCKET,
        "objectKey": object_key,
    }


def oss_uri(bucket: str, object_key: str) -> str:
    return f"oss://{bucket}/{object_key}"


def parse_oss_uri(storage_path: str) -> tuple[str, str] | None:
    if not storage_path or not storage_path.startswith("oss://"):
        return None
    rest = storage_path[6:]
    if "/" not in rest:
        return None
    bucket, key = rest.split("/", 1)
    return bucket, key


def head_object(object_key: str) -> bool:
    import alibabacloud_oss_v2 as oss

    from backend.app.core.config import settings

    client = _get_client()
    try:
        client.head_object(
            oss.HeadObjectRequest(bucket=settings.OSS_BUCKET, key=object_key),
        )
        return True
    except Exception as exc:
        logger.warning("OSS head_object 失败 key=%s: %s", object_key, exc)
        return False


def download_to_path(object_key: str, local_path: Path) -> Path:
    import alibabacloud_oss_v2 as oss

    from backend.app.core.config import settings

    client = _get_client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.get_object_to_file(
        oss.GetObjectRequest(bucket=settings.OSS_BUCKET, key=object_key),
        str(local_path),
    )
    return local_path


def delete_object(object_key: str) -> None:
    import alibabacloud_oss_v2 as oss

    from backend.app.core.config import settings

    client = _get_client()
    try:
        client.delete_object(
            oss.DeleteObjectRequest(bucket=settings.OSS_BUCKET, key=object_key),
        )
    except Exception as exc:
        logger.warning("OSS delete_object 失败 key=%s: %s", object_key, exc)
