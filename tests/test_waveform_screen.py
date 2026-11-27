import io

import numpy as np
import soundfile as sf
import pytest

from audiobook.waveform_screen import screen
from audiobook.chapter_quality import build
import json


def wav(x):
    buf=io.BytesIO()
    sf.write(buf,x,16000,format="WAV",subtype="FLOAT")
    return buf.getvalue()


@pytest.mark.parametrize("x,expected",[
    (np.zeros(16000),"digital_silence"),
    (np.full(16000,.2),"dc_offset"),
    (np.tile([-1.,1.],8000),"near_full_scale_peak"),
])
def test_waveform_diagnostic_signals(x,expected):
    result=screen(wav(x))
    assert result["status"]=="measured"
    assert expected in result["signals"]
    assert result["diagnostic_only"] is True


def test_decode_failure_and_no_false_perceptual_pass():
    assert screen(b"invalid")["status"]=="invalid"
    result=screen(wav(.1*np.sin(2*np.pi*200*np.arange(16000)/16000)))
    assert result["status"]=="measured" and result["signals"]==[]
    m=json.dumps(dict(id="01",hash="h",text="Мама.",status="done")).encode()
    report,rows=build(m,{"01":"a"*64},waveforms={"01":result})
    assert rows[0]["priority"]=="unverified"
    assert report["human_coverage"]["artifacts"]=={"unmeasured":1}
    _,rows=build(m,{"01":"a"*64},waveforms={"01":screen(b"invalid")})
    assert rows[0]["priority"]=="incomplete"
