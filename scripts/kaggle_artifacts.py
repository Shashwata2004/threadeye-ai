"""Version-pinned private Kaggle outputs; signed URLs never leave this process.

The CLI currently parses a ref's version but omits it from status/output requests. Use this
small SDK wrapper so an unrelated running revision cannot hide a completed frozen dataset.
"""

import argparse
import re
from pathlib import Path

import requests
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (
    ApiGetKernelSessionStatusRequest,
    ApiListKernelSessionOutputRequest,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "download"])
    parser.add_argument("ref")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pattern", default=".*")
    args = parser.parse_args()
    parts = args.ref.split("/")
    assert len(parts) in (2, 3)
    api = KaggleApi()
    api.authenticate()
    with api.build_kaggle_client() as client:
        if args.action == "status":
            request = ApiGetKernelSessionStatusRequest()
            request.user_name, request.kernel_slug = parts[:2]
            if len(parts) == 3:
                request.version_label = parts[2]
            print(client.kernels.kernels_api_client.get_kernel_session_status(request))
            return
        assert args.out is not None
        token = None
        count = 0
        while True:
            request = ApiListKernelSessionOutputRequest()
            request.user_name, request.kernel_slug = parts[:2]
            if len(parts) == 3:
                request.version_label = parts[2]
            request.page_size = 100
            if token:
                request.page_token = token
            response = client.kernels.kernels_api_client.list_kernel_session_output(
                request
            )
            for file in response.files or []:
                if not re.search(args.pattern, file.file_name):
                    continue
                relative = Path(file.file_name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe output path")
                destination = args.out / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with requests.get(file.url, stream=True, timeout=(30, 180)) as stream:
                        if stream.status_code != 200:
                            raise RuntimeError(
                                f"artifact download returned HTTP {stream.status_code}"
                            )
                        temporary = destination.with_name(destination.name + ".partial")
                        with temporary.open("wb") as output:
                            for chunk in stream.iter_content(1024 * 1024):
                                output.write(chunk)
                        temporary.replace(destination)
                except requests.RequestException:
                    raise RuntimeError("artifact download connection failed") from None
                count += 1
            token = response.next_page_token
            if not token:
                break
        if not count:
            raise ValueError("no matching output files were downloaded")
        print("Downloaded", count, "version-pinned artifacts")


if __name__ == "__main__":
    main()
