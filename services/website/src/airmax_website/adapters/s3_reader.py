from pathlib import Path


class S3Reader:
    def __init__(self, bucket: str):
        import boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def result(self) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key="results/latest.json")[
            "Body"
        ].read()

    def municipalities(self) -> bytes:
        path = Path(__file__).parents[1] / "reference" / "municipalities.geojson"
        return path.read_bytes()
