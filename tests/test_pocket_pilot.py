from types import SimpleNamespace
import numpy as np
import pytest

from audiobook.pocket_pilot import CASES, collect_audio, make_plan


class Tokenizer:
    def get_vocab(self):
        return {}

    def encode(self, text, add_special_tokens=False):
        return SimpleNamespace(ids=[ord(c)+1 for c in text])

    def decode(self, ids, skip_special_tokens=False):
        return "".join(chr(i-1) for i in ids)


class Engine:
    max_frames = 125
    samples_per_frame = 4

    def tokens(self, ipa):
        return np.array([1, 2])

    def stream(self, items, seed, stop):
        yield ("audio", 0, np.ones(8, dtype=np.float32))
        yield ("end", 0, {"frames": 2, "stopped": False})


def test_frozen_plan_marker_only():
    plan = make_plan(Tokenizer(), {"revision": "a"*40}, "r", "s", {})
    assert len(plan["trials"]) == len(CASES) == 4
    for t in plan["trials"]:
        assert t["baseline"].replace("ˈ", "") == t["candidate"].replace("ˈ", "")
        assert t["baseline_tokens"] != t["candidate_tokens"]


def test_collect_complete_stream():
    assert len(collect_audio(Engine(), "ipa", None, 42, [1, 2])) == 8
    with pytest.raises(ValueError, match="CONDITIONER"):
        collect_audio(Engine(), "ipa", None, 42, [2, 1])


@pytest.mark.parametrize("end", [{"frames": 125, "stopped": False},
                                 {"frames": 2, "stopped": True},
                                 {"frames": 3, "stopped": False}])
def test_bad_stream(end):
    class Broken(Engine):
        def stream(self, items, seed, stop):
            yield ("audio", 0, np.ones(8, dtype=np.float32))
            yield ("end", 0, end)
    with pytest.raises(ValueError, match="INCOMPLETE|FRAME_LENGTH"):
        collect_audio(Broken(), "ipa", None, 42, [1, 2])
