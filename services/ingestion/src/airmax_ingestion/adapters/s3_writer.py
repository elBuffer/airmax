import json


class S3Writer:
    def __init__(self, bucket: str):
        import boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def write(self, key: str, event: dict) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode(),
            ContentType="application/json",
        )
