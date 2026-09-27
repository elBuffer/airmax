import json
from dataclasses import dataclass
from datetime import datetime

from botocore.exceptions import ClientError


@dataclass(frozen=True)
class RawObject:
    key: str
    modified: datetime


class S3Store:
    def __init__(self, raw_bucket: str, results_bucket: str):
        import boto3

        self.raw_bucket = raw_bucket
        self.results_bucket = results_bucket
        self.s3 = boto3.client("s3")

    def raw_objects(
        self, prefix: str, start_after: str = "", stop_at: str | None = None
    ) -> list[RawObject]:
        """Keys under prefix, in key order, after start_after and before stop_at."""
        paginator = self.s3.get_paginator("list_objects_v2")
        objects: list[RawObject] = []
        for page in paginator.paginate(
            Bucket=self.raw_bucket, Prefix=prefix, StartAfter=start_after
        ):
            for item in page.get("Contents", []):
                if stop_at is not None and item["Key"] >= stop_at:
                    return objects
                objects.append(RawObject(item["Key"], item["LastModified"]))
        return objects

    def read_text(self, key: str) -> str:
        return (
            self.s3.get_object(Bucket=self.raw_bucket, Key=key)["Body"].read().decode()
        )

    def read_result(self) -> tuple[dict | None, str | None]:
        try:
            response = self.s3.get_object(
                Bucket=self.results_bucket, Key="results/latest.json"
            )
            return json.loads(response["Body"].read()), response["ETag"]
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None, None
            raise

    def write_result(self, value, etag: str | None) -> bool:
        condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
        try:
            self.s3.put_object(
                Bucket=self.results_bucket,
                Key="results/latest.json",
                Body=json.dumps(
                    value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode(),
                ContentType="application/json",
                **condition,
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
                "412",
                "409",
            ):
                return False
            raise
