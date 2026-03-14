from backend.pipelines.meet_bot import start_meet_bot
import asyncio

async def main():
    MEET_LINK = "https://meet.google.com/gqh-ebue-zno"
    OUTPUT_AUDIO = r"backend\speech\temp\meeting_audio.wav"
    TRANSCRIPT_OUTPUT = r"backend\speech\temp\transcript.txt"
    
    await start_meet_bot(MEET_LINK, OUTPUT_AUDIO, TRANSCRIPT_OUTPUT)

if __name__ == "__main__":
    asyncio.run(main())
