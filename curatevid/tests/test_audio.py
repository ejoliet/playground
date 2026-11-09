"""Integration check catches PyAV/faster-whisper decoder API incompatibility."""
import subprocess
from faster_whisper.audio import decode_audio


def test_whisper_audio_decode(tmp_path):
    audio = tmp_path/'audio.wav'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1',
                    '-ar','16000','-ac','1',str(audio)],check=True)
    samples = decode_audio(str(audio))
    assert samples.shape == (16000,)
