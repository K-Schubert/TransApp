import asyncio
import websockets
import torch
import whisper
import json
import os
import wave
import deepl
from dotenv import load_dotenv

load_dotenv()

# Load DeepL API key for translation
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", None)
translator = deepl.Translator(DEEPL_API_KEY)

# Load Whisper model on GPU (use GPU 3 if available)
model = whisper.load_model("turbo")

async def transcribe_audio(websocket, path):
    """Handles WebSocket connection and streams audio data for transcription."""
    audio_buffer = bytearray()  # Buffer to store audio chunks

    try:
        print(f"New WebSocket connection from {websocket.remote_address}")  # Debug connection info

        async for message in websocket:
            if isinstance(message, bytes):  # Ensure we're handling binary audio data
                print(f"Received binary audio chunk of size: {len(message)} bytes")
                audio_buffer.extend(message)  # Add chunk to the buffer

                # Check if we have enough data (5 seconds of audio)
                if len(audio_buffer) >= 16000 * 2 * 5:  # Process every 5 seconds of 16-bit mono audio (WAV)
                    print(f"Processing audio buffer of size: {len(audio_buffer)} bytes for transcription...")

                    # Save the buffer to a temporary WAV file for transcription
                    temp_filename = "temp_audio.wav"
                    with wave.open(temp_filename, "wb") as f:
                        f.setnchannels(1)  # Mono audio
                        f.setsampwidth(2)  # 16-bit audio
                        f.setframerate(16000)  # 16 kHz sample rate
                        f.writeframes(audio_buffer)

                    print("WAV file created. Running Whisper model for transcription...")

                    # Use Whisper to transcribe the WAV audio buffer
                    result = model.transcribe(temp_filename, language='de', task='translate')
                    transcription = result['text']
                    print(f"Transcription result: {transcription}")

                    if not transcription.strip():
                        print("Transcription is empty.")
                        # Send a message back to the client indicating no speech was detected
                        response = {"transcription": "No speech detected."}
                        await websocket.send(json.dumps(response))
                    else:
                        # Translate the transcription using DeepL
                        translation = translator.translate_text(transcription, target_lang="EN-GB")
                        print(f"Translated text: {translation.text}")

                        # Send the translated transcription back to the client
                        response = {"transcription": translation.text}
                        await websocket.send(json.dumps(response))
                        print("Transcription sent to client")

                    # Clear the buffer after processing
                    audio_buffer.clear()

                    # Clean up the temporary file
                    os.remove(temp_filename)
                    print("Temporary WAV file removed")
            else:
                print(f"Received unexpected non-binary message: {message}")

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error occurred: {e}")


# Start the WebSocket server
async def main():
    async with websockets.serve(transcribe_audio, "0.0.0.0", 42331):
        print("WebSocket server started at port 42331...")
        await asyncio.Future()  # Run forever

# Run the WebSocket server
if __name__ == "__main__":
    asyncio.run(main())
