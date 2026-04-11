from pyannote.audio import Pipeline
import soundfile as sf
import torch
import numpy as np
import os
from dotenv import load_dotenv

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

audio_path = "experiments/meeting.wav"

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN
)

# Load audio with soundfile instead of torchaudio
waveform, sample_rate = sf.read(audio_path, dtype="float32")

# soundfile returns (time, channels), pyannote needs (channels, time)
waveform = torch.tensor(waveform).T
if waveform.ndim == 1:
    waveform = waveform.unsqueeze(0)  # mono: add channel dim

audio_input = {"waveform": waveform, "sample_rate": sample_rate}

diarization = pipeline(audio_input)

print("\n--- SPEAKERS ---\n")
for turn, _, speaker in diarization.speaker_diarization.itertracks(yield_label=True):
    print(f"{turn.start:.2f} - {turn.end:.2f} : {speaker}")

