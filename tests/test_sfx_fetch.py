"""Offline SFX candidate download tests; no network or private media."""
import hashlib
import io
import json
from pathlib import Path
import runpy

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sfx_fetch.py"
API = runpy.run_path(str(SCRIPT))


class Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, data, redirect=False):
        self.data = data
        self.redirect = redirect

    def open(self, request, timeout):
        return Response(self.data, "https://example.invalid" if self.redirect else request.full_url)


def inventory(tmp_path, data=b"OggS-synthetic", **changes):
    row = dict(id="fixture", license="CC0-1.0", author="Synthetic",
               source="https://commons.wikimedia.org/wiki/File:fixture.ogg",
               url="https://upload.wikimedia.org/wikipedia/commons/a/aa/fixture.ogg",
               bytes=len(data), source_sha1=hashlib.sha1(data, usedforsecurity=False).hexdigest())
    row.update(changes)
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(dict(schema="sfx-candidate-inventory-v1",
                                    status="candidate_only", assets=[row])), encoding="utf-8")
    return path


def test_download_hash_and_receipt(tmp_path):
    data = b"OggS-synthetic"
    manifest = inventory(tmp_path, data)
    out = tmp_path / "candidates"
    receipt = API["download"](out, manifest, FakeOpener(data))
    assert (out / "fixture.ogg").read_bytes() == data
    assert receipt["assets"][0]["sha256"] == hashlib.sha256(data).hexdigest()
    assert receipt["release_ready"] is False
    assert json.loads((out / "receipt.json").read_text(encoding="utf-8")) == receipt
    with pytest.raises(FileExistsError):
        API["download"](out, manifest, FakeOpener(data))


@pytest.mark.parametrize("data,redirect", [(b"OggS-corrupted", False), (b"longer than expected input", False), (b"OggS-synthetic", True)])
def test_bad_download_never_publishes(tmp_path, data, redirect):
    manifest = inventory(tmp_path)
    out = tmp_path / "candidates"
    with pytest.raises(ValueError):
        API["download"](out, manifest, FakeOpener(data, redirect))
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("changes", [dict(id="../outside"), dict(license="CC-BY-NC"), dict(url="https://example.invalid/fixture.ogg")])
def test_bad_inventory_rejected_before_output(tmp_path, changes):
    manifest = inventory(tmp_path, **changes)
    out = tmp_path / "candidates"
    with pytest.raises(ValueError):
        API["download"](out, manifest, FakeOpener(b""))
    assert not out.exists()


def test_committed_candidates_contract():
    path = SCRIPT.parents[1] / "sfx" / "public-candidates.json"
    rows = API["validate_inventory"](json.loads(path.read_text(encoding="utf-8")))
    assert len(rows) == 2
