"""Build AWS Lambda ZIP files without requiring ECR access."""

import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("ingestion", "transformation", "website")


def main() -> None:
    work = ROOT / ".local" / "lambda-build"
    shutil.rmtree(work, ignore_errors=True)

    for service in SERVICES:
        stage = work / service
        if service == "transformation":
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--target",
                    str(stage),
                    "--python-platform",
                    "x86_64-manylinux2014",
                    "--python-version",
                    "3.12",
                    "--only-binary",
                    ":all:",
                    "shapely==2.1.2",
                ],
                check=True,
            )
        shutil.copytree(
            ROOT / "services" / service / "src" / f"airmax_{service}",
            stage / f"airmax_{service}",
        )

        artifact = ROOT / "infra" / "terraform" / f"{service}.zip"
        with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in stage.rglob("*"):
                if path.is_file() and path.name != ".lock":
                    archive.write(path, path.relative_to(stage))
        print(f"Built {artifact.relative_to(ROOT)}")

    shutil.rmtree(work)


if __name__ == "__main__":
    main()
