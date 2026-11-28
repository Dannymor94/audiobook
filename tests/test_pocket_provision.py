from types import SimpleNamespace
import hashlib

import pytest

from audiobook.pocket_provision import PUBLIC_FILES, expected_files, verify_download


def blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data,
                        usedforsecurity=False).hexdigest()


def fixture():
    data = b"public fixture"
    siblings = []
    for name in PUBLIC_FILES:
        siblings.append(SimpleNamespace(rfilename=name, size=len(data),
                            lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest())
                            if name == "model.safetensors" else None,
                            blob_id=blob(data)))
    return SimpleNamespace(sha="a"*40, card_data={"license": "cc-by-4.0"},
                           siblings=siblings), data


def test_publisher_digests(tmp_path):
    info, data = fixture()
    expected = expected_files(info)
    for name in PUBLIC_FILES:
        p = tmp_path / name
        p.write_bytes(data)
        assert verify_download(p, expected[name]) == hashlib.sha256(data).hexdigest()
    p.write_bytes(b"x"*len(data))
    with pytest.raises(ValueError, match="PUBLISHER_DIGEST_MISMATCH"):
        verify_download(p, expected[name])


def test_license_and_weight_digest_required():
    info, _ = fixture()
    info.card_data["license"] = "cc-by-nc-4.0"
    with pytest.raises(ValueError, match="LICENSE"):
        expected_files(info)
    info.card_data["license"] = "cc-by-4.0"
    info.siblings[-1].lfs = None
    with pytest.raises(ValueError, match="WEIGHT_LFS"):
        expected_files(info)
