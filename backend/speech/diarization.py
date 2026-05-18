"""Diarized transcription helpers for recorded meeting audio."""

from __future__ import annotations

import logging
import os
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf
import torch
from dotenv import load_dotenv
from scipy.spatial.distance import cosine

logger = logging.getLogger(__name__)

DEFAULT_SPEAKER_DB = "speaker_db.pkl"
DEFAULT_THRESHOLD = 0.35

_diarization_pipeline: Optional[Any] = None
_asr_model: Optional[Any] = None
_voice_encoder: Optional[Any] = None


@dataclass
class SpeakerIdentificationRequest:
    """Speaker sample that needs a human-provided display name."""

    speaker_id: str
    sample_path: str
    start: float
    end: float


@dataclass
class DiarizationSession:
    """In-memory diarization state used while Telegram collects speaker names."""

    audio_path: str
    diarization: Any
    speaker_map: dict[str, str]
    speaker_embeddings: dict[str, np.ndarray]
    unknown_speakers: list[SpeakerIdentificationRequest] = field(default_factory=list)
    speaker_db_path: str = DEFAULT_SPEAKER_DB
    whisper_model: str = "base"
    device: str = "cpu"


def transcribe_audio_with_diarization(
    audio_path: str,
    *,
    speaker_db_path: str = DEFAULT_SPEAKER_DB,
    threshold: float = DEFAULT_THRESHOLD,
    whisper_model: str = "base",
    allow_new_speaker_prompts: bool = False,
    timestamped_output_path: Optional[str] = None,
) -> str:
    """
    Transcribe audio and prefix each merged segment with an identified speaker.

    Unknown pyannote speakers are matched against ``speaker_db_path`` using
    resemblyzer embeddings. In bot mode, unknown speakers are kept as
    ``SPEAKER_00`` etc. so the Telegram pipeline never blocks on input().
    """
    session = prepare_diarization_session(
        audio_path,
        sample_output_dir=None,
        speaker_db_path=speaker_db_path,
        threshold=threshold,
        whisper_model=whisper_model,
        allow_new_speaker_prompts=False,
    )
    names = {}
    if allow_new_speaker_prompts:
        for request in session.unknown_speakers:
            entered = input(
                f"Enter name for {request.speaker_id} "
                f"[{request.start:.1f}s-{request.end:.1f}s] "
                f"(or press Enter to keep '{request.speaker_id}'): "
            ).strip()
            names[request.speaker_id] = entered or request.speaker_id

    return transcribe_prepared_diarization(
        session,
        speaker_names=names,
        timestamped_output_path=timestamped_output_path,
    )


def prepare_diarization_session(
    audio_path: str,
    *,
    sample_output_dir: Optional[str],
    speaker_db_path: str = DEFAULT_SPEAKER_DB,
    threshold: float = DEFAULT_THRESHOLD,
    whisper_model: str = "base",
    allow_new_speaker_prompts: bool = False,
) -> DiarizationSession:
    """Run diarization and prepare unknown-speaker samples for review."""
    load_dotenv()

    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Preparing diarization on %s using %s", audio_path, device)

    full_waveform, full_sample_rate = sf.read(str(audio_file), dtype="float32")
    mono_waveform = full_waveform.mean(axis=1) if full_waveform.ndim > 1 else full_waveform

    waveform_tensor = torch.tensor(full_waveform).T
    if waveform_tensor.ndim == 1:
        waveform_tensor = waveform_tensor.unsqueeze(0)
    audio_input = {"waveform": waveform_tensor, "sample_rate": full_sample_rate}

    diarization = _load_diarization_pipeline(device)(audio_input)
    diarization = _normalise_diarization_output(diarization)

    speaker_db = _load_speaker_db(speaker_db_path)
    speaker_map, embeddings, unknown_speakers = _build_speaker_map(
        diarization=diarization,
        mono_waveform=mono_waveform,
        full_waveform=full_waveform,
        sample_rate=full_sample_rate,
        speaker_db=speaker_db,
        speaker_db_path=speaker_db_path,
        threshold=threshold,
        device=device,
        allow_new_speaker_prompts=allow_new_speaker_prompts,
        sample_output_dir=sample_output_dir,
    )

    return DiarizationSession(
        audio_path=str(audio_file),
        diarization=diarization,
        speaker_map=speaker_map,
        speaker_embeddings=embeddings,
        unknown_speakers=unknown_speakers,
        speaker_db_path=speaker_db_path,
        whisper_model=whisper_model,
        device=device,
    )


def transcribe_prepared_diarization(
    session: DiarizationSession,
    *,
    speaker_names: Optional[dict[str, str]] = None,
    timestamped_output_path: Optional[str] = None,
) -> str:
    """Resume transcription after optional human speaker identification."""
    speaker_names = speaker_names or {}
    speaker_map = dict(session.speaker_map)
    speaker_db = _load_speaker_db(session.speaker_db_path)

    changed_db = False
    for speaker_id, display_name in speaker_names.items():
        name = display_name.strip() or speaker_id
        speaker_map[speaker_id] = name
        embedding = session.speaker_embeddings.get(speaker_id)
        if embedding is not None and name != speaker_id:
            speaker_db[name] = embedding
            changed_db = True

    if changed_db:
        _save_speaker_db(session.speaker_db_path, speaker_db)

    asr_result = _load_asr_model(session.whisper_model, session.device).transcribe(session.audio_path)
    merged = _align_and_merge_segments(asr_result["segments"], session.diarization, speaker_map)

    if timestamped_output_path:
        _write_timestamped_transcript(timestamped_output_path, merged)

    return "\n".join(f"{entry['speaker']}: {entry['text']}" for entry in merged)


def _load_diarization_pipeline(device: str) -> Any:
    global _diarization_pipeline
    if _diarization_pipeline is not None:
        return _diarization_pipeline

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise ValueError("HF_TOKEN is required for pyannote speaker diarization.")

    try:
        from pyannote.audio import Pipeline
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "pyannote.audio is required for diarization. Install project "
            "dependencies in the bot environment, then restart the bot."
        ) from exc

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    pipeline.to(torch.device(device))
    _diarization_pipeline = pipeline
    return pipeline


def _load_asr_model(model_name: str, device: str) -> Any:
    global _asr_model
    if _asr_model is None:
        try:
            import whisper

            _asr_model = whisper.load_model(model_name, device=device)
        except ModuleNotFoundError:
            from faster_whisper import WhisperModel

            compute_type = "float16" if device == "cuda" else "int8"
            _asr_model = _FasterWhisperAdapter(
                WhisperModel(model_name, device=device, compute_type=compute_type)
            )
    return _asr_model


class _FasterWhisperAdapter:
    """Expose faster-whisper through the subset of OpenAI Whisper API we use."""

    def __init__(self, model: Any):
        self.model = model

    def transcribe(self, audio_path: str) -> dict[str, list[dict[str, Any]]]:
        segments, _ = self.model.transcribe(audio_path)
        return {
            "segments": [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
                for segment in segments
            ]
        }


def _load_voice_encoder(device: str) -> Any:
    global _voice_encoder
    if _voice_encoder is None:
        try:
            from resemblyzer import VoiceEncoder
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "resemblyzer is required for speaker name matching. Install it "
                "in the bot environment, then restart the bot."
            ) from exc

        _voice_encoder = VoiceEncoder(device=device)
    return _voice_encoder


def _normalise_diarization_output(diarization: Any) -> Any:
    if hasattr(diarization, "itertracks"):
        return diarization
    if hasattr(diarization, "speaker_diarization"):
        return diarization.speaker_diarization
    if hasattr(diarization, "annotation"):
        return diarization.annotation
    raise TypeError("Unsupported pyannote diarization output.")


def _load_speaker_db(path: str) -> dict[str, np.ndarray]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        logger.warning("Could not load speaker DB %s; starting empty", path)
        return {}


def _save_speaker_db(path: str, speaker_db: dict[str, np.ndarray]) -> None:
    with open(path, "wb") as f:
        pickle.dump(speaker_db, f)


def _build_speaker_map(
    *,
    diarization: Any,
    mono_waveform: np.ndarray,
    full_waveform: np.ndarray,
    sample_rate: int,
    speaker_db: dict[str, np.ndarray],
    speaker_db_path: str,
    threshold: float,
    device: str,
    allow_new_speaker_prompts: bool,
    sample_output_dir: Optional[str],
) -> tuple[dict[str, str], dict[str, np.ndarray], list[SpeakerIdentificationRequest]]:
    encoder = _load_voice_encoder(device)
    try:
        from resemblyzer import preprocess_wav
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "resemblyzer is required for speaker name matching. Install it "
            "in the bot environment, then restart the bot."
        ) from exc

    embeddings_by_speaker = defaultdict(list)
    best_segments: dict[str, tuple[float, float, float]] = {}

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        duration = turn.end - turn.start
        if duration < 0.3:
            continue

        start_sample = int(turn.start * sample_rate)
        end_sample = int(turn.end * sample_rate)
        segment = mono_waveform[start_sample:end_sample]
        wav = preprocess_wav(segment, source_sr=sample_rate)
        embeddings_by_speaker[speaker].append(encoder.embed_utterance(wav))

        if speaker not in best_segments or duration > best_segments[speaker][2]:
            best_segments[speaker] = (turn.start, turn.end, duration)

    speaker_map = {}
    speaker_embeddings = {}
    unknown_speakers = []
    changed_db = False

    for speaker, embeddings in embeddings_by_speaker.items():
        avg_embedding = np.mean(embeddings, axis=0)
        speaker_embeddings[speaker] = avg_embedding
        name, score = _identify_speaker(avg_embedding, speaker_db, threshold)

        if name:
            speaker_map[speaker] = name
            speaker_db[name] = 0.8 * speaker_db[name] + 0.2 * avg_embedding
            changed_db = True
            logger.info("Matched %s to %s (distance %.3f)", speaker, name, score)
            continue

        if allow_new_speaker_prompts:
            start, end, _ = best_segments[speaker]
            entered = input(
                f"Enter name for {speaker} [{start:.1f}s-{end:.1f}s] "
                f"(or press Enter to keep '{speaker}'): "
            ).strip()
            name = entered or speaker
            speaker_db[name] = avg_embedding
            changed_db = True
        else:
            name = speaker
            if speaker in best_segments:
                start, end, _ = best_segments[speaker]
                sample_path = ""
                if sample_output_dir:
                    sample_path = _write_speaker_sample(
                        sample_output_dir,
                        speaker,
                        full_waveform,
                        sample_rate,
                        start,
                        end,
                    )
                unknown_speakers.append(
                    SpeakerIdentificationRequest(
                        speaker_id=speaker,
                        sample_path=sample_path,
                        start=start,
                        end=end,
                    )
                )

        speaker_map[speaker] = name

    if changed_db:
        _save_speaker_db(speaker_db_path, speaker_db)

    return speaker_map, speaker_embeddings, unknown_speakers


def _write_speaker_sample(
    output_dir: str,
    speaker: str,
    full_waveform: np.ndarray,
    sample_rate: int,
    start: float,
    end: float,
) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    sample_duration = min(max(end - start, 1.5), 8.0)
    sample_start = start
    sample_end = min(start + sample_duration, end)
    start_sample = int(sample_start * sample_rate)
    end_sample = int(sample_end * sample_rate)
    sample = full_waveform[start_sample:end_sample]
    path = Path(output_dir) / f"{speaker}.wav"
    sf.write(str(path), sample, sample_rate)
    return str(path)


def _identify_speaker(
    embedding: np.ndarray,
    speaker_db: dict[str, np.ndarray],
    threshold: float,
) -> tuple[Optional[str], float]:
    best_match = None
    best_score = 1.0
    for name, known_embedding in speaker_db.items():
        score = cosine(embedding, known_embedding)
        if score < best_score:
            best_score = score
            best_match = name
    if best_score < threshold:
        return best_match, best_score
    return None, best_score


def _align_and_merge_segments(
    asr_segments: list[dict[str, Any]],
    diarization: Any,
    speaker_map: dict[str, str],
) -> list[dict[str, Any]]:
    final_output = []
    for segment in asr_segments:
        speaker = _get_speaker_for_segment(
            segment["start"],
            segment["end"],
            diarization,
            speaker_map,
        )
        final_output.append(
            {
                "speaker": speaker,
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip(),
            }
        )

    for index, entry in enumerate(final_output):
        if entry["speaker"] != "UNKNOWN":
            continue
        next_known = next(
            (item["speaker"] for item in final_output[index + 1 :] if item["speaker"] != "UNKNOWN"),
            None,
        )
        previous_known = next(
            (item["speaker"] for item in reversed(final_output[:index]) if item["speaker"] != "UNKNOWN"),
            None,
        )
        entry["speaker"] = next_known or previous_known or "UNKNOWN"

    merged = []
    for entry in final_output:
        if merged and merged[-1]["speaker"] == entry["speaker"]:
            merged[-1]["text"] += " " + entry["text"]
            merged[-1]["end"] = entry["end"]
        else:
            merged.append(dict(entry))

    return merged


def _get_speaker_for_segment(
    start: float,
    end: float,
    diarization: Any,
    speaker_map: dict[str, str],
) -> str:
    overlap = defaultdict(float)
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        overlap_seconds = min(turn.end, end) - max(turn.start, start)
        if overlap_seconds > 0:
            overlap[speaker] += overlap_seconds
    if not overlap:
        return "UNKNOWN"
    best_speaker = max(overlap, key=overlap.get)
    return speaker_map.get(best_speaker, best_speaker)


def _write_timestamped_transcript(path: str, entries: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(
                f"[{entry['start']:.1f}s - {entry['end']:.1f}s] "
                f"{entry['speaker']}: {entry['text']}\n"
            )
