from types import SimpleNamespace
import json

import pytest

from audiobook.pocket_preflight import FILES, PROBES, sha, verify_assets, verify_token_channel


class Tokenizer:
    def get_vocab(self):
        return {"<unk>": 0}

    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return SimpleNamespace(ids=[ord(c)+1 for c in text])

    def decode(self, ids, skip_special_tokens=False):
        assert skip_special_tokens is False
        return "".join(chr(i-1) for i in ids)


def test_lossless_stress_channel():
    results = verify_token_channel(Tokenizer())
    assert len(results) == len(PROBES)
    assert all(r["a_ids"] != r["b_ids"] for r in results)


@pytest.mark.parametrize("kind", ["strip", "unknown", "range"])
def test_bad_token_channel(kind):
    class Broken(Tokenizer):
        def encode(self, text, add_special_tokens=False):
            if kind == "strip":
                return super().encode(text.replace("ˈ", ""))
            return SimpleNamespace(ids=[0 if kind == "unknown" else 4000])
    with pytest.raises(ValueError, match="NOT_LOSSLESS"):
        verify_token_channel(Broken())


def test_asset_identity_and_stress_manifest(tmp_path):
    for name in FILES:
        (tmp_path / name).write_bytes(b"fixture")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"languages": ["ru"], "keep_stress": True}))
    inv = {"repo_id": "gabrione/pocket-tts-phonemes-multilang",
           "revision": "a"*40, "files": {n: sha(tmp_path/n) for n in FILES}}
    assert verify_assets(tmp_path, inv)["revision"] == "a"*40
    manifest.write_text(json.dumps({"languages": ["ru"], "keep_stress": False}))
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        verify_assets(tmp_path, inv)
    inv["files"]["manifest.json"] = sha(manifest)
    with pytest.raises(ValueError, match="STRESS_TRAINING_NOT_DECLARED"):
        verify_assets(tmp_path, inv)
