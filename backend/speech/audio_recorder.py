import os
import time
import wave
import pyaudiowpatch as pyaudio
import threading

CHUNK = 4096

def record_system_audio(output_path, stop_event=None, record_seconds=None):
    print("===== AUDIO RECORDER INITIALIZING =====", flush=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    p = pyaudio.PyAudio()
    
    try:
        print("[AUDIO] Getting default WASAPI loopback device...", flush=True)
        device = p.get_default_wasapi_loopback()
        print(f"[AUDIO] Using device: {device['name']} (Index: {device['index']})", flush=True)
    except OSError as e:
        print(f"[AUDIO] CRITICAL ERROR: Could not get default wasapi loopback device: {e}", flush=True)
        p.terminate()
        return

    RATE = int(device["defaultSampleRate"])
    CHANNELS = device["maxInputChannels"]
    print(f"[AUDIO] Config: {RATE}Hz, {CHANNELS} channels", flush=True)

    try:
        print("[AUDIO] Opening stream...", flush=True)
        stream = p.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=CHUNK
        )
        print("[AUDIO] Stream opened successfully.", flush=True)
    except Exception as e:
        print(f"[AUDIO] CRITICAL ERROR: Could not open stream: {e}", flush=True)
        p.terminate()
        return

    if record_seconds:
        total_iterations = int(RATE / CHUNK * record_seconds)
    else:
        total_iterations = int(RATE / CHUNK * 3600 * 10)

    print(f"[AUDIO] Opening WAV file at {output_path}...", flush=True)
    wf = wave.open(output_path, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)

    print("===== AUDIO RECORDING STARTED =====", flush=True)
    start = time.time()
    frames_recorded = 0
    for i in range(total_iterations):
        if stop_event and stop_event.is_set():
            print("[AUDIO] Stop event detected. Finishing recording.", flush=True)
            break

        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if data:
                wf.writeframes(data)
                frames_recorded += 1
        except Exception as e:
            print(f"[AUDIO] Stream read error: {e}", flush=True)
            continue

        elapsed = int(time.time() - start)
        if i % int(RATE / CHUNK * 10) == 0:
            print(f"[AUDIO DEBUG] Recording... Elapsed: {elapsed}s, Frames: {frames_recorded}", flush=True)

    print(f"[AUDIO] Stopping recording after {frames_recorded} frames...", flush=True)
    stream.stop_stream()
    stream.close()
    p.terminate()
    wf.close()

    actual_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print("===== AUDIO SAVED =====", flush=True)
    print(f"Final file size: {actual_size} bytes ({frames_recorded} chunks)", flush=True)
    print("File path:", os.path.abspath(output_path), flush=True)
