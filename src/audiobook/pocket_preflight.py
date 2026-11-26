"""Read-only ALG-04 Pocket IPA input preflight. No model or TTS calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

FILES = ("model.yaml", "manifest.json", "tokenizer.json", "model.safetensors")
# Synthetic strings: token-channel probes, not normative Russian transcriptions.
PROBES = (("ˈmama", "maˈma"), ("ˈzamak", "zaˈmak"),
          ("ˈbar sʊki", "bar ˈsʊki"), ("ˈtʲest", "tʲest"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_assets(root: Path, inventory: dict) -> dict:
    if inventory.get("repo_id") != "gabrione/pocket-tts-phonemes-multilang":
        raise ValueError("WRONG_MODEL_REPO")
    revision = inventory.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("FULL_MODEL_REVISION_REQUIRED")
    files = inventory["files"]
    if set(files) != set(FILES):
        raise ValueError("EXACT_ASSET_INVENTORY_REQUIRED")
    actual = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("REGULAR_LOCAL_ASSET_REQUIRED:" + name)
        actual[name] = sha(path)
        if actual[name] != files[name]:
            raise ValueError("ASSET_DIGEST_MISMATCH:" + name)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if ("ru" not in manifest.get("languages", [])
            or manifest.get("keep_stress") is not True):
        raise ValueError("RUSSIAN_STRESS_TRAINING_NOT_DECLARED")
    return {"revision": revision, "files": actual}


def verify_token_channel(tokenizer, probes=PROBES, n_bins: int = 4000) -> list[dict]:
    """Exact reversible encoding, no special/unknown IDs, distinct stress inputs.

    Byte fallback is allowed: the upstream training recipe used it for stress
    marks. This tests the channel only, not whether the model obeys it.
    """
    vocab = tokenizer.get_vocab()
    special = {i for t, i in vocab.items()
               if t in {"<unk>", "<pad>", "<s>", "</s>", "[UNK]", "[PAD]"}}
    results = []
    for a, b in probes:
        if a.replace("ˈ", "") != b.replace("ˈ", "") or a == b:
            raise ValueError("NOT_STRESS_ONLY_CONTRAST")
        encoded = []
        for ipa in (a, b):
            ids = tokenizer.encode(ipa, add_special_tokens=False).ids
            if (not ids or any(type(i) is not int or not 0 <= i < n_bins
                               or i in special for i in ids)
                    or tokenizer.decode(ids, skip_special_tokens=False) != ipa):
                raise ValueError("IPA_TOKEN_CHANNEL_NOT_LOSSLESS")
            encoded.append(ids)
        if encoded[0] == encoded[1]:
            raise ValueError("STRESS_TOKEN_COLLISION")
        results.append({"a": a, "b": b, "a_ids": encoded[0], "b_ids": encoded[1]})
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--inventory-sha256", required=True)
    a = p.parse_args()
    if sha(a.inventory) != a.inventory_sha256:
        raise ValueError("INVENTORY_DIGEST_MISMATCH")
    inventory = json.loads(a.inventory.read_bytes())
    identity = verify_assets(a.model_dir, inventory)
    import yaml
    from tokenizers import Tokenizer
    config = yaml.safe_load((a.model_dir / "model.yaml").read_bytes())
    # Upstream model_config intentionally overrides the base text lookup with
    # a 4000-bin IPA vocabulary; base YAML's original bin count is not evidence.
    tok = Tokenizer.from_file(str(a.model_dir / "tokenizer.json"))
    probes = verify_token_channel(tok)
    if verify_assets(a.model_dir, inventory) != identity:
        raise ValueError("ASSETS_CHANGED")
    print(json.dumps({"identity": identity, "token_channel": probes,
                      "base_config_is_mapping": isinstance(config, dict),
                      "status": "TOKEN_CHANNEL_ONLY_NO_ACOUSTIC_CLAIM"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
