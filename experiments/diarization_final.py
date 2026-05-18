from pyannote.audio import Pipeline
import soundfile as sf
import torch
import whisper
import numpy as np
from collections import defaultdict
import pickle
import os
from dotenv import load_dotenv
from resemblyzer import VoiceEncoder, preprocess_wav
from scipy.spatial.distance import cosine
import warnings
warnings.filterwarnings("ignore", category=UserWarning)


load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

audio_path = "experiments/meeting_1.wav"
DB_PATH = "speaker_db.pkl"
THRESHOLD = 0.35

# ------------------------
# Load models
# ------------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

print("Loading diarization model...")
pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN
)
pipeline.to(torch.device(device))

print("Loading whisper model...")
asr_model = whisper.load_model("base", device=device)

encoder = VoiceEncoder(device=device)

# ------------------------
# Load audio
# ------------------------
full_waveform, full_sample_rate = sf.read(audio_path, dtype="float32")
mono_waveform = full_waveform.mean(axis=1) if full_waveform.ndim > 1 else full_waveform

# For pyannote — needs (channels, time) torch tensor
waveform_tensor = torch.tensor(full_waveform).T
if waveform_tensor.ndim == 1:
    waveform_tensor = waveform_tensor.unsqueeze(0)
audio_input = {"waveform": waveform_tensor, "sample_rate": full_sample_rate}

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

def identify_speaker(embedding):
    best_match = None
    best_score = 1.0
    for name, emb in speaker_db.items():
        score = cosine(embedding, emb)
        print(f"    comparing with '{name}': distance = {score:.3f}")
        if score < best_score:
            best_score = score
            best_match = name
    if best_score < THRESHOLD:
        return best_match, best_score
    return None, best_score

def extract_segment(start, end):
    start_sample = int(start * full_sample_rate)
    end_sample = int(end * full_sample_rate)
    return mono_waveform[start_sample:end_sample]

# ------------------------
# Step 1: Diarization
# ------------------------
print("Running diarization...")
diarization_output = pipeline(audio_input)

# Safely extract Annotation object
diarization = diarization_output
if not hasattr(diarization, "itertracks"):
    if hasattr(diarization, "speaker_diarization"):
        diarization = diarization.speaker_diarization
    elif hasattr(diarization, "annotation"):
        diarization = diarization.annotation

print("\n--- RAW DIARIZATION ---")
for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(f"{turn.start:.2f} - {turn.end:.2f} : {speaker}")

# ------------------------
# Step 2: Build embeddings per speaker (averaged across all segments)
# ------------------------
print("\nBuilding speaker embeddings...")
speaker_embeddings_list = defaultdict(list)

for turn, _, speaker in diarization.itertracks(yield_label=True):
    if (turn.end - turn.start) < 0.3:
        continue
    segment = extract_segment(turn.start, turn.end)
    wav = preprocess_wav(segment, source_sr=full_sample_rate)
    emb = encoder.embed_utterance(wav)
    speaker_embeddings_list[speaker].append(emb)

speaker_avg_embeddings = {
    speaker: np.mean(embs, axis=0)
    for speaker, embs in speaker_embeddings_list.items()
}

# ------------------------
# Step 3: Identify or prompt for speaker names
# ------------------------
# Find longest segment per speaker for timestamp reference
best_segments = {}
for turn, _, speaker in diarization.itertracks(yield_label=True):
    duration = turn.end - turn.start
    if speaker not in best_segments or duration > best_segments[speaker][2]:
        best_segments[speaker] = (turn.start, turn.end, duration)

print("\n--- IDENTIFY SPEAKERS ---")
print("Open your audio file and jump to the timestamps below to identify each speaker.\n")

speaker_map = {}
new_speakers = {}  # stage new speakers, save after all are identified

for speaker in sorted(speaker_avg_embeddings.keys()):
    avg_emb = speaker_avg_embeddings[speaker]
    name, score = identify_speaker(avg_emb)

    if name:
        print(f"  {speaker} matched to known speaker '{name}' (distance: {score:.3f})")
        speaker_map[speaker] = name
        # Update embedding with running average
        speaker_db[name] = 0.8 * speaker_db[name] + 0.2 * avg_emb
    else:
        start, end, duration = best_segments[speaker]
        print(f"\n  {speaker}: longest segment [{start:.1f}s - {end:.1f}s] ({duration:.1f}s)")
        other_segments = [
            (t.start, t.end)
            for t, _, s in diarization.itertracks(yield_label=True)
            if s == speaker and (t.end - t.start) > 1.0
        ][:3]
        if other_segments:
            print(f"    Other segments: {', '.join(f'[{s:.1f}s-{e:.1f}s]' for s, e in other_segments)}")

        entered_name = input(f"  Enter name for {speaker} (or press Enter to keep '{speaker}'): ").strip()
        name = entered_name if entered_name else speaker
        new_speakers[name] = avg_emb
        speaker_map[speaker] = name
        print()

# Save all new speakers at once
for name, emb in new_speakers.items():
    speaker_db[name] = emb
save_speaker_db()
print(f"\nSaved {len(new_speakers)} new speaker(s) to DB.")

print("\nSpeaker map:")
for speaker, name in speaker_map.items():
    print(f"  {speaker} -> {name}")

# ------------------------
# Step 4: Transcription
# ------------------------
print("\nRunning transcription...")
asr_result = asr_model.transcribe(audio_path)

# ------------------------
# Step 5: Align transcription with speakers using overlap
# ------------------------
def get_speaker_for_segment(start, end, diarization, speaker_map):
    overlap = defaultdict(float)
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        o = min(turn.end, end) - max(turn.start, start)
        if o > 0:
            overlap[speaker] += o
    if not overlap:
        return "UNKNOWN"
    best_speaker = max(overlap, key=overlap.get)
    return speaker_map.get(best_speaker, best_speaker)

final_output = []
for seg in asr_result["segments"]:
    speaker = get_speaker_for_segment(seg["start"], seg["end"], diarization, speaker_map)
    final_output.append({
        "speaker": speaker,
        "start": seg["start"],
        "end": seg["end"],
        "text": seg["text"].strip()
    })

# ------------------------
# Step 6: Merge UNKNOWN into the next known speaker
# ------------------------
# First pass: assign UNKNOWN to the next known speaker
for i, entry in enumerate(final_output):
    if entry["speaker"] == "UNKNOWN":
        # Look ahead for next known speaker
        for j in range(i + 1, len(final_output)):
            if final_output[j]["speaker"] != "UNKNOWN":
                entry["speaker"] = final_output[j]["speaker"]
                break
        else:
            # No next speaker found, look back instead
            for j in range(i - 1, -1, -1):
                if final_output[j]["speaker"] != "UNKNOWN":
                    entry["speaker"] = final_output[j]["speaker"]
                    break

# ------------------------
# Step 7: Merge consecutive same-speaker lines
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
print("\n--- TRANSCRIPT ---\n")
for entry in merged:
    print(f"[{entry['start']:.1f}s - {entry['end']:.1f}s] {entry['speaker']}: {entry['text']}")

# Save timestamped transcript
timestamped_path = audio_path.replace(".wav", "_transcript_timestamped.txt")
with open(timestamped_path, "w", encoding="utf-8") as f:
    for entry in merged:
        f.write(f"[{entry['start']:.1f}s - {entry['end']:.1f}s] {entry['speaker']}: {entry['text']}\n")

# Save clean transcript (name: text only)
clean_path = audio_path.replace(".wav", "_transcript.txt")
with open(clean_path, "w", encoding="utf-8") as f:
    for entry in merged:
        f.write(f"{entry['speaker']}: {entry['text']}\n")

print(f"\nTimestamped transcript saved to: {timestamped_path}")
print(f"Clean transcript saved to: {clean_path}")