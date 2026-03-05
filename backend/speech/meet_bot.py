import asyncio
import os
import time
import wave
import pyaudiowpatch as pyaudio
from playwright.async_api import async_playwright

MEET_LINK = "https://meet.google.com/gqh-ebue-zno"

OUTPUT_AUDIO = r"backend\speech\temp\meeting_audio.wav"

RECORD_SECONDS = 10
CHUNK = 4096  # ~85 ms at 48kHz


# =========================
# AUDIO RECORDING
# =========================

def record_system_audio():

    print("===== AUDIO RECORDING STARTED =====")

    os.makedirs(os.path.dirname(OUTPUT_AUDIO), exist_ok=True)

    p = pyaudio.PyAudio()

    device = p.get_default_wasapi_loopback()

    print("Using device:", device["name"])
    print("Device info:", device)

    RATE = int(device["defaultSampleRate"])
    CHANNELS = device["maxInputChannels"]

    print("Audio config:")
    print("RATE:", RATE)
    print("CHANNELS:", CHANNELS)
    print("CHUNK:", CHUNK)

    stream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        input_device_index=device["index"],
        frames_per_buffer=CHUNK
    )

    total_iterations = int(RATE / CHUNK * RECORD_SECONDS)

    print("Total iterations:", total_iterations)

    # open wav file immediately
    wf = wave.open(OUTPUT_AUDIO, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)

    start = time.time()

    for i in range(total_iterations):

        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            print("Stream read error:", e)
            continue

        wf.writeframes(data)

        elapsed = int(time.time() - start)

        if elapsed % 1 == 0 and i % int(RATE / CHUNK) == 0:
            print(f"[AUDIO DEBUG] Recording second {elapsed}")

    print("Stopping recording...")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf.close()

    print("===== AUDIO SAVED =====")
    print("File path:", os.path.abspath(OUTPUT_AUDIO))


# =========================
# GOOGLE MEET BOT
# =========================

async def join_meeting():

    try:

        async with async_playwright() as p:

            print("Launching Chrome...")

            context = await p.chromium.launch_persistent_context(
                user_data_dir="backend/speech/chrome_bot_profile",
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--start-maximized"
                ]
            )

            page = await context.new_page()

            page.on("close", lambda: print("PAGE CLOSED"))
            context.on("close", lambda: print("CONTEXT CLOSED"))

            print("Opening Google Meet...")
            await page.goto(MEET_LINK)

            await page.wait_for_timeout(5000)

            # -----------------------------
            # 1️⃣ Click "Got it" popup
            # -----------------------------
            try:
                got_it = page.locator('button:has-text("Got it")')
                if await got_it.is_visible(timeout=3000):
                    print("Clicking 'Got it' popup")
                    await got_it.click()
            except:
                print("No 'Got it' popup")

            await page.wait_for_timeout(5000)

            # -----------------------------
            # 2️⃣ Disable microphone
            # -----------------------------
            print("Disabling microphone")

            try:
                await page.keyboard.press("Control+d")
            except:
                print("Mic toggle failed")

            await page.wait_for_timeout(2000)

            # -----------------------------
            # 3️⃣ Enter name
            # -----------------------------
            try:
                print("Entering name: bot")

                name_input = page.locator('input[placeholder="Your name"]')

                await name_input.fill("bot")

            except Exception as e:
                print("Name input failed:", e)

            await page.wait_for_timeout(1000)

            # -----------------------------
            # 4️⃣ Join meeting
            # -----------------------------
            print("Joining meeting...")

            try:
                await page.locator('button:has-text("Join now")').click(timeout=5000)
                print("Joined meeting")

            except:

                try:
                    await page.locator('button:has-text("Ask to join")').click(timeout=5000)
                    print("Requested to join meeting")

                except:
                    print("Join button not found")
            
            # -----------------------------
            # 2️⃣ Disable microphone again
            # -----------------------------
            print("Disabling microphone 2")

            try:
                await page.keyboard.press("Control+d")
            except:
                print("Mic toggle failed")

            await page.wait_for_timeout(2000)

            print("Meeting bot running...")

            while True:
                print("[BOT DEBUG] Meeting still active...")
                await asyncio.sleep(5)

    except Exception as e:
        print("BOT CRASH:", e)

# =========================
# MAIN PIPELINE
# =========================

async def main():

    meeting_task = asyncio.create_task(join_meeting())

    # wait for meeting to start
    await asyncio.sleep(15)

    # run recording in parallel thread
    recording_task = asyncio.to_thread(record_system_audio)

    await asyncio.gather(recording_task, meeting_task)


if __name__ == "__main__":
    asyncio.run(main())