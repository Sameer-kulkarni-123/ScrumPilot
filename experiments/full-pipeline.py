import os
import pickle
import warnings
import numpy as np
from collections import defaultdict
from dotenv import load_dotenv
from pyannote.audio import Pipeline
import whisper
from resemblyzer import VoiceEncoder, preprocess_wav
from scipy.spatial.distance import cosine
import soundfile as sf
import torch

# Suppress torchcodec warning since we're using soundfile
warnings.filterwarnings("ignore", message="torchcodec is not installed correctly")

# ------------------------
# Config
# ------------------------
DB_PATH = "speaker_db.pkl"
THRESHOLD = 0.75        # cosine distance threshold — lower = stricter matching
MIN_SEGMENT_LEN = 0.3   # seconds — skip segments shorter than this

# ------------------------
# Load env
# ------------------------
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
audio_path = "experiments/meeting.wav"

# ------------------------
# Load models
# ------------------------
print("Loading models...")
diar_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN
)
asr_model = whisper.load_model("base")
encoder = VoiceEncoder()

# ------------------------
# Load full audio once (avoids re-reading file for every segment)
# ------------------------
print("Loading audio...")
full_waveform, full_sample_rate = sf.read(audio_path, dtype="float32")
if full_waveform.ndim > 1:
    full_waveform = full_waveform.mean(axis=1)  # mix down to mono

def load_audio_for_diarization(path):
    """Load audio as torch tensor dict for pyannote."""
    waveform, sample_rate = sf.read(path, dtype="float32")
    waveform = torch.tensor(waveform).T
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    return {"waveform": waveform, "sample_rate": sample_rate}

def extract_segment(start, end):
    """Extract a slice of the preloaded waveform."""
    start_sample = int(start * full_sample_rate)
    end_sample = int(end * full_sample_rate)
    return full_waveform[start_sample:end_sample], full_sample_rate

# ------------------------
# Load speaker DB
# ------------------------
speaker_db = {}
if os.path.exists(DB_PATH):
    try:
        with open(DB_PATH, "rb") as f:
            speaker_db = pickle.load(f)
        print(f"Loaded {len(speaker_db)} known speakers: {list(speaker_db.keys())}")
    except Exception:
        print("Corrupted speaker DB, resetting...")
        speaker_db = {}

def save_speaker_db():
    with open(DB_PATH, "wb") as f:
        pickle.dump(speaker_db, f)

# ------------------------
# Helper: identify speaker from embedding
# ------------------------
def identify_speaker(embedding):
    best_match = None
    best_score = 1.0
    for name, emb in speaker_db.items():
        score = cosine(embedding, emb)
        if score < best_score:
            best_score = score
            best_match = name
    if best_score < THRESHOLD:
        return best_match
    return None

# ------------------------
# Helper: update speaker DB with running average
# ------------------------
def update_speaker_db(name, new_emb):
    if name in speaker_db:
        # Weight existing embedding more heavily than new one
        speaker_db[name] = 0.8 * speaker_db[name] + 0.2 * new_emb
    else:
        speaker_db[name] = new_emb
    save_speaker_db()

# ------------------------
# Helper: get speaker for ASR segment using overlap
# ------------------------
def get_speaker_for_segment(start, end, diarization, speaker_map):
    overlap = defaultdict(float)
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        o = min(turn.end, end) - max(turn.start, start)
        if o > 0:
            overlap[speaker] += o
    if not overlap:
        return "Unknown"
    best_speaker = max(overlap, key=overlap.get)
    return speaker_map.get(best_speaker, best_speaker)

# ------------------------
# Step 1: Diarization
# ------------------------
print("Running diarization...")
audio_input = load_audio_for_diarization(audio_path)
diarization_output = diar_pipeline(audio_input, min_speakers=1, max_speakers=10)
diarization = diarization_output.speaker_diarization

# ------------------------
# Step 2: Collect all embeddings per speaker across all segments
# ------------------------
print("Building speaker embeddings...")
speaker_embeddings = defaultdict(list)

for turn, _, speaker in diarization.itertracks(yield_label=True):
    if (turn.end - turn.start) < MIN_SEGMENT_LEN:
        continue
    segment_wav, sample_rate = extract_segment(turn.start, turn.end)
    wav = preprocess_wav(segment_wav, source_sr=sample_rate)
    emb = encoder.embed_utterance(wav)
    speaker_embeddings[speaker].append(emb)

# ------------------------
# Step 3: Average embeddings and build speaker map
# ------------------------
print("Identifying speakers...")
speaker_map = {}

for speaker, embeddings in speaker_embeddings.items():
    avg_emb = np.mean(embeddings, axis=0)
    name = identify_speaker(avg_emb)

    if name is None:
        print(f"\nNew speaker detected: {speaker}")
        name = input("Enter name: ").strip()

    update_speaker_db(name, avg_emb)
    speaker_map[speaker] = name
    print(f"  {speaker} -> {name}")

# ------------------------
# Step 4: ASR
# ------------------------
print("\nRunning transcription...")
asr_result = asr_model.transcribe(audio_path)

# ------------------------
# Step 5: Merge diarization + transcription using overlap
# ------------------------
final_output = []

for seg in asr_result["segments"]:
    name = get_speaker_for_segment(
        seg["start"], seg["end"], diarization, speaker_map
    )
    final_output.append({
        "speaker": name,
        "start": seg["start"],
        "end": seg["end"],
        "text": seg["text"].strip()
    })

# ------------------------
# Step 6: Merge consecutive same-speaker segments
# ------------------------
merged = []
for entry in final_output:
    if merged and merged[-1]["speaker"] == entry["speaker"]:
        merged[-1]["text"] += " " + entry["text"]
        merged[-1]["end"] = entry["end"]
    else:
        merged.append(dict(entry))

# ------------------------
# Output
# ------------------------
print("\n--- FINAL OUTPUT ---\n")
for entry in merged:
    print(f"[{entry['start']:.1f}s - {entry['end']:.1f}s] {entry['speaker']}: {entry['text']}")

# ------------------------
# Save output to file
# ------------------------
output_path = audio_path.replace(".wav", "_transcript.txt")
with open(output_path, "w", encoding="utf-8") as f:
    for entry in merged:
        f.write(f"[{entry['start']:.1f}s - {entry['end']:.1f}s] {entry['speaker']}: {entry['text']}\n")

print(f"\nTranscript saved to: {output_path}")