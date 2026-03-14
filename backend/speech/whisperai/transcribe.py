import whisper


def transcribe_audio_from_path(filename: str):
  """ input: path to audio file
      output: transcribed text"""

  model = whisper.load_model("turbo")
  result = model.transcribe(filename)
  return result["text"]


if __name__ == '__main__':
  test_filename = r"backend\speech\whisperai\temp\meeting_audio.wav"
  text = transcribe_audio_from_path(test_filename)
  print(text)
