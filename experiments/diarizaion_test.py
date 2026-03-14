from pyannote.audio import Pipeline
from dotenv import load_dotenv
import os

# load .env file
load_dotenv()

# get token
HF_TOKEN = os.getenv("HF_TOKEN")

AUDIO_FILE = "backend/speech/temp/meeting_audio.wav"

print("Loading diarization pipeline...")

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN
)

print("Running diarization...")

diarization = pipeline(AUDIO_FILE)

print("Results:")

for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(
        f"{turn.start:.2f} - {turn.end:.2f} : {speaker}"
    )