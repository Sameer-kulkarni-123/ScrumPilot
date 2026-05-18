from pyannote.audio import Pipeline
from dotenv import load_dotenv
import os

# load .env file
load_dotenv()

# get token
HF_TOKEN = os.getenv("HF_TOKEN")

AUDIO_FILE = "backend/speech/temp/meeting.wav"

import torch

print("Loading diarization pipeline...")

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Moving pipeline to device: {device}")
pipeline.to(device)

import soundfile as sf

print("Loading audio file in-memory...")
waveform, sample_rate = sf.read(AUDIO_FILE, dtype="float32")
waveform_tensor = torch.tensor(waveform).T
if waveform_tensor.ndim == 1:
    waveform_tensor = waveform_tensor.unsqueeze(0)
audio_input = {"waveform": waveform_tensor, "sample_rate": sample_rate}

print("Running diarization...")

diarization = pipeline(audio_input)

# Handle Pyannote 3.1 returning DiarizeOutput instead of direct Annotation
if not hasattr(diarization, "itertracks"):
    if hasattr(diarization, "speaker_diarization"):
        diarization = diarization.speaker_diarization
    elif hasattr(diarization, "annotation"):
        diarization = diarization.annotation

print("Results:")

for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(
        f"{turn.start:.2f} - {turn.end:.2f} : {speaker}"
    )