"""Download and verify the two pinned public Volare model packages.

Run with: uv run --with zstandard python prepare_models.py --output <cache>
The cache and PDK archives belong outside the Git repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

import zstandard

PIN = "c6d73a35f524070e85faff4a6a9eef49553ebc2b"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    url = f"https://api.github.com/repos/chipfoundry/volare/releases/tags/sky130-{PIN}"
    with urllib.request.urlopen(url, timeout=60) as response:
        release = json.load(response)
    packages = [asset for asset in release["assets"] if asset["name"] in
                ("common.tar.zst", "sky130_fd_pr.tar.zst")]
    records = []
    for asset in packages:
        archive = output / asset["name"]
        expected = asset["digest"].removeprefix("sha256:")
        if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            print(f"Downloading {asset['name']}: {asset['size']} bytes", flush=True)
            urllib.request.urlretrieve(asset["browser_download_url"], archive)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Digest mismatch: {archive}")
        with archive.open("rb") as source:
            with zstandard.ZstdDecompressor().stream_reader(source) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as tar:
                    count = 0
                    for member in tar:
                        # Keep only SPICE runtime content, including model dependencies.
                        name = member.name
                        if "/libs.tech/combined/" in name or "/libs.ref/sky130_fd_pr/spice/" in name:
                            tar.extract(member, path=output / "pdk", filter="data")
                            count += 1
        records.append({"name": asset["name"], "sha256": actual,
                        "source": asset["browser_download_url"], "members_extracted": count})
        print(f"Extracted {count} model members from {asset['name']}", flush=True)
    (output / "model_packages.json").write_text(json.dumps({"open_pdks_commit": PIN, "packages": records}, indent=2))
    with tarfile.open(output / "sky130-models.tar.gz", "w:gz") as tar:
        tar.add(output / "pdk", arcname="pdk")
    print(f"Transfer archive: {output / 'sky130-models.tar.gz'}", flush=True)


if __name__ == "__main__":
    main()
