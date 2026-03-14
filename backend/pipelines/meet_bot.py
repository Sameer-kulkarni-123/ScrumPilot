import asyncio
import os

from backend.speech.audio_recorder import record_system_audio
from backend.meeting.meet_client import join_meeting
from backend.speech.whisperai.transcribe import transcribe_audio_from_path

#set these params in main.py
# MEET_LINK = "https://meet.google.com/gqh-ebue-zno"
# OUTPUT_AUDIO = r"backend\speech\temp\meeting_audio.wav"
# TRANSCRIPT_OUTPUT = r"backend\speech\temp\transcript.txt"

import threading

async def start_meet_bot(MEET_LINK, OUTPUT_AUDIO, TRANSCRIPT_OUTPUT):
    print("===== STARTING PIPELINE =====", flush=True)
    
    stop_event = threading.Event()
    
    # 1. Start meeting bot
    meeting_task = asyncio.create_task(join_meeting(MEET_LINK))
    
    # Wait for meeting to start and bot to join
    await asyncio.sleep(15)
    
    # 2. Run recording
    print("Starting audio recording...", flush=True)
    # We must create a task for the thread so it runs concurrently with the awaited meeting_task
    recording_task = asyncio.create_task(asyncio.to_thread(record_system_audio, OUTPUT_AUDIO, stop_event=stop_event))
    
    # Wait for the meeting bot to finish (which happens when it's alone for > 30s)
    await meeting_task
    
    # After meeting ends, stop recording
    print("Meeting ended or left. Stopping audio recording...", flush=True)
    stop_event.set()
    await recording_task
    
    # 3. Transcribe audio
    print(f"Starting transcription of {OUTPUT_AUDIO}...", flush=True)
    try:
        text = transcribe_audio_from_path(OUTPUT_AUDIO)
        
        print("===== TRANSCRIPTION RESULT =====", flush=True)
        print(text, flush=True)
        
        # 4. Store transcription
        os.makedirs(os.path.dirname(TRANSCRIPT_OUTPUT), exist_ok=True)
        with open(TRANSCRIPT_OUTPUT, "w", encoding="utf-8") as f:
            f.write(text)
            
        print(f"Transcription saved to {TRANSCRIPT_OUTPUT}", flush=True)
    except Exception as e:
        print(f"Error during transcription: {e}", flush=True)
        
    print("===== PIPELINE COMPLETED =====", flush=True)

if __name__ == "__main__":
    asyncio.run(start_meet_bot(MEET_LINK, OUTPUT_AUDIO, TRANSCRIPT_OUTPUT))