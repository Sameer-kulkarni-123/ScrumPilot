import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

model = WhisperModel("base", device="cpu")

SAMPLE_RATE = 16000
CHUNK_DURATION = 10  # seconds


def record_chunk():
    audio = sd.rec(int(CHUNK_DURATION * SAMPLE_RATE),
                   samplerate=SAMPLE_RATE,
                   channels=1,
                   dtype='float32')
    sd.wait()
    return audio.flatten()


def live_transcribe():

    print("recording audio")
    audio = record_chunk()
    print("finished recording audio")

    segments, info = model.transcribe(audio)

    return segments




if __name__ == '__main__':
    for _ in range(10):
        segments = live_transcribe()
        
        for segment in segments:
            print(segment.text)