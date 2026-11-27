"""Download only the reviewed public SFX candidates; no production writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_REJECTED")


def validate_inventory(data):
    if data["schema"] != "sfx-candidate-inventory-v1" or data["status"] != "candidate_only":
        raise ValueError("INVALID_INVENTORY")
    assets = data["assets"]
    if not 1 <= len(assets) <= 8:
        raise ValueError("INVALID_COUNT")
    seen = set()
    for row in assets:
        name = row["id"]
        url = urlsplit(row["url"])
        if (not re.fullmatch(r"[a-z0-9-]{1,48}", name) or name in seen
                or row["license"] != "CC0-1.0"
                or url.scheme != "https" or url.netloc != "upload.wikimedia.org"
                or not url.path.startswith("/wikipedia/commons/")
                or not url.path.endswith(".ogg") or url.query or url.fragment
                or type(row["bytes"]) is not int or not 1 <= row["bytes"] <= 10_000_000
                or not re.fullmatch(r"[a-f0-9]{40}", row["source_sha1"])):
            raise ValueError("INVALID_ASSET")
        seen.add(name)
    return assets


def fetch_one(row, out, opener):
    final = out / (row["id"] + ".ogg")
    part = out / (row["id"] + ".ogg.part")
    source_hash = hashlib.sha1(usedforsecurity=False)
    digest = hashlib.sha256()
    size = 0
    request = Request(row["url"], headers={"User-Agent": "AudiobookSFXCandidate/1.0 (manual public CC0 download)"})
    try:
        with opener.open(request, timeout=30) as response, part.open("xb") as target:
            if response.geturl() != row["url"]:
                raise ValueError("URL_CHANGED")
            while chunk := response.read(64 * 1024):
                size += len(chunk)
                if size > row["bytes"]:
                    raise ValueError("SIZE_MISMATCH")
                source_hash.update(chunk)
                digest.update(chunk)
                target.write(chunk)
        if size != row["bytes"] or source_hash.hexdigest() != row["source_sha1"]:
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        part.replace(final)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return dict(id=row["id"], file=final.name, bytes=size, sha256=digest.hexdigest(),
                source_sha1=row["source_sha1"], source=row["source"],
                author=row["author"], license=row["license"])


def download(out: Path, inventory: Path, opener=None):
    raw = inventory.read_bytes()
    assets = validate_inventory(json.loads(raw))
    out.mkdir(exist_ok=False)
    opener = opener or build_opener(NoRedirect())
    rows = [fetch_one(row, out, opener) for row in assets]
    receipt = dict(schema="sfx-candidate-receipt-v1", status="downloaded_unreviewed",
                   inventory_sha256=hashlib.sha256(raw).hexdigest(),
                   release_ready=False, assets=rows)
    tmp = out / "receipt.json.part"
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out / "receipt.json")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new local candidate directory")
    args = parser.parse_args()
    inventory = Path(__file__).resolve().parents[1] / "sfx" / "public-candidates.json"
    receipt = download(args.out, inventory)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
