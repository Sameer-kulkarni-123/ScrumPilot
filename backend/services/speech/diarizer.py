import os
import torch
import torchaudio
import soundfile as sf
from pyannote.audio import Pipeline
from dotenv import load_dotenv

load_dotenv()

class ScrumDiarizer:
    def __init__(self):
        """
        Initializes the Pyannote Diarization pipeline.
        Requires HF_TOKEN in .env and access to gated models on Hugging Face.
        """
        print("📥 Loading Diarization Pipeline (Windows-Safe Mode)...")
        
        token = os.getenv("HF_TOKEN")
        if not token:
            print("❌ ERROR: HF_TOKEN not found in .env")
            return

        try:
            # Note: 'use_auth_token' was changed to 'token' in version 3.1+
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=token
            )
            
            # Move to GPU if available for faster processing
            if torch.cuda.is_available():
                self.pipeline.to(torch.device("cuda"))
                print("🚀 Using GPU for diarization.")
            else:
                print("⚠️ Running on CPU. Diarization will be slower.")
                
        except Exception as e:
            print(f"❌ Initialization Failed: {e}")

    def process_audio(self, audio_path):
        """
        Processes audio for speaker diarization. 
        Uses soundfile directly to bypass buggy torchaudio/torchcodec dispatchers on Windows.
        """
        print(f"🎬 Starting diarization for: {audio_path}")
        
        if not os.path.exists(audio_path):
            print(f"❌ File not found: {audio_path}")
            return []

        try:
            # 1. Load audio using soundfile directly
            data, sample_rate = sf.read(audio_path)
            
            # 2. Convert to Torch Tensor (channels, samples)
            waveform = torch.from_numpy(data).float()
            
            # Handle multi-channel (Stereo to Mono)
            if len(waveform.shape) > 1:
                waveform = waveform.mean(dim=1).unsqueeze(0)
            else:
                waveform = waveform.unsqueeze(0)
            
            # Check for very short audio to avoid pooling errors
            duration = waveform.shape[1] / sample_rate
            if duration < 2.0:  # Increased threshold for stability
                print(f"⚠️ Audio is only {duration:.1f}s. Diarization needs at least ~2 seconds of speech.")
                return []

            # 3. Format the data for Pyannote's in-memory processing
            audio_in_memory = {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
            
            # 4. Run the pipeline
            print("⏳ Analyzing voices (this may take a few minutes)...")
            diarization = self.pipeline(audio_in_memory)
            
            # 5. Extract the Annotation object
            # Pyannote 3.1 can return a 'DiarizeOutput' object or a 'pyannote.core.Annotation'
            annotation = None
            
            if hasattr(diarization, "itertracks"):
                annotation = diarization
            elif hasattr(diarization, "annotation"):
                annotation = diarization.annotation
            elif isinstance(diarization, dict) and "annotation" in diarization:
                annotation = diarization["annotation"]

            results = []
            if annotation and hasattr(annotation, "itertracks"):
                for turn, _, speaker in annotation.itertracks(yield_label=True):
                    results.append({
                        "start": turn.start,
                        "end": turn.end,
                        "speaker": speaker
                    })
                    print(f"[{turn.start:.1f}s - {turn.end:.1f}s] {speaker}")
            
            if not results:
                print("ℹ️ No speakers detected. The audio might be silent or contains only one person for the entire duration.")
                # Fallback: If no segments found but audio exists, assume Speaker 0 for the whole duration
                results.append({"start": 0, "end": duration, "speaker": "SPEAKER_00"})
                
            return results
            
        except Exception as e:
            print(f"❌ Diarization Error: {e}")
            import traceback
            traceback.print_exc()
            return []

if __name__ == "__main__":
    # Local Test Block
    diarizer = ScrumDiarizer()
    
    # Try to get path from .env, otherwise use default
    test_file = os.getenv("OUTPUT_AUDIO_PATH")
    if not test_file or not os.path.exists(test_file):
        test_file = r"backend\speech\temp\meeting_audio.wav"

    if os.path.exists(test_file):
        diarizer.process_audio(test_file)
    else:
        print(f"❌ Test audio file not found at {test_file}. Please record a meeting first!")