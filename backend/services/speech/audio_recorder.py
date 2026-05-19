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

    frames = []
    
    # Callback to handle incoming audio frames in a separate pyaudio thread
    def callback(in_data, frame_count, time_info, status):
        if in_data:
            frames.append(in_data)
        return (None, pyaudio.paContinue)

    try:
        print("[AUDIO] Opening stream in non-blocking callback mode...", flush=True)
        stream = p.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=CHUNK,
            stream_callback=callback
        )
        print("[AUDIO] Stream opened successfully.", flush=True)
    except Exception as e:
        print(f"[AUDIO] CRITICAL ERROR: Could not open stream: {e}", flush=True)
        p.terminate()
        return

    print("===== AUDIO RECORDING STARTED =====", flush=True)
    stream.start_stream()
    
    start_time = time.time()
    last_debug_time = start_time
    
    try:
        while stream.is_active():
            if stop_event and stop_event.is_set():
                print("[AUDIO] Stop event detected. Finishing recording.", flush=True)
                break
            if record_seconds and (time.time() - start_time) >= record_seconds:
                print(f"[AUDIO] Recording duration limit reached: {record_seconds}s.", flush=True)
                break
                
            # Print debug log every 10 seconds
            current_time = time.time()
            if current_time - last_debug_time >= 10:
                elapsed = int(current_time - start_time)
                print(f"[AUDIO DEBUG] Recording... Elapsed: {elapsed}s, Chunks: {len(frames)}", flush=True)
                last_debug_time = current_time
                
            time.sleep(0.1)
    except Exception as e:
        print(f"[AUDIO] Recording loop exception: {e}", flush=True)

    print(f"[AUDIO] Stopping recording...", flush=True)
    try:
        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"[AUDIO] Error closing stream: {e}", flush=True)

    print(f"[AUDIO] Opening WAV file at {output_path}...", flush=True)
    try:
        wf = wave.open(output_path, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(RATE)
        
        # Write all accumulated frames
        for frame in frames:
            wf.writeframes(frame)
        wf.close()
    except Exception as e:
        print(f"[AUDIO] Error writing WAV file: {e}", flush=True)

    p.terminate()

    actual_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print("===== AUDIO SAVED =====", flush=True)
    print(f"Final file size: {actual_size} bytes ({len(frames)} chunks)", flush=True)
    print("File path:", os.path.abspath(output_path), flush=True)
