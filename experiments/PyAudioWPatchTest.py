import pyaudiowpatch as pyaudio
import wave
import time

print("Initializing PyAudio...")

p = pyaudio.PyAudio()

print("Fetching default WASAPI loopback device...")

device = p.get_default_wasapi_loopback()

print("Device info:", device)

RATE = int(device["defaultSampleRate"])
CHANNELS = device["maxInputChannels"]
CHUNK = 1024
SECONDS = 100

OUTPUT = "PyAudioWPatchTest_sound.wav"

print("Configuration:")
print("  RATE:", RATE)
print("  CHANNELS:", CHANNELS)
print("  CHUNK:", CHUNK)
print("  SECONDS:", SECONDS)

print("Opening stream...")

stream = p.open(
    format=pyaudio.paInt16,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=device["index"]
)

print("Stream opened successfully")

frames = []

total_iterations = int(RATE / CHUNK * SECONDS)

print("Total iterations:", total_iterations)

print("Starting recording...")

start_time = time.time()

for i in range(total_iterations):

    print(f"[DEBUG] Reading chunk {i+1}/{total_iterations}")

    try:
        data = stream.read(CHUNK, exception_on_overflow=False)
    except Exception as e:
        print("Stream read error:", e)
        continue

    frames.append(data)

    elapsed = time.time() - start_time

    print(
        f"[DEBUG] chunk={i+1} "
        f"bytes={len(data)} "
        f"elapsed={elapsed:.2f}s"
    )

    if i % int(RATE / CHUNK) == 0:
        print(f"[SECOND DEBUG] ~{int(elapsed)} seconds recorded")

print("Stopping stream...")

stream.stop_stream()
stream.close()

print("Terminating PyAudio...")

p.terminate()

print("Saving WAV file...")

wf = wave.open(OUTPUT, "wb")
wf.setnchannels(CHANNELS)
wf.setsampwidth(2)
wf.setframerate(RATE)
wf.writeframes(b"".join(frames))
wf.close()

print("Saved:", OUTPUT)