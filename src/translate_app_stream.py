import sys
import os
import json
import sounddevice as sd
import numpy as np
import wave
import asyncio
import websockets
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize, Qt, QThread, pyqtSignal
from queue import Queue
from dotenv import load_dotenv
load_dotenv()

TRANSCRIPTION_ENDPOINT = os.environ.get("TRANSCRIPTION_ENDPOINT", None)


def resource_path(relative_path):
    """ Get the absolute path to a resource, works for both development and PyInstaller. """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        return os.path.join(os.path.abspath("."), relative_path)

class WebSocketThread(QThread):
    update_transcription = pyqtSignal(str)

    def __init__(self, uri, audio_queue, parent=None):
        super().__init__(parent)
        self.uri = uri
        self.is_streaming = False
        self.audio_queue = audio_queue
        self.websocket = None
        self.loop = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.stream_audio())
        finally:
            self.loop.close()

    async def stream_audio(self):
        try:
            print(f"Connecting to WebSocket server: {self.uri}")
            async with websockets.connect(self.uri) as websocket:
                self.websocket = websocket
                print(f"Connected to WebSocket server: {self.uri}")
                self.is_streaming = True

                send_task = asyncio.ensure_future(self.send_audio(websocket))
                recv_task = asyncio.ensure_future(self.receive_transcription(websocket))
                await asyncio.gather(send_task, recv_task)
        except Exception as e:
            print(f"Error during WebSocket connection: {e}")

    async def send_audio(self, websocket):
        while self.is_streaming:
            if not self.audio_queue.empty():
                audio_chunk = self.audio_queue.get()
                print(f"Sending audio chunk of size: {len(audio_chunk)}")
                await websocket.send(audio_chunk)
            else:
                await asyncio.sleep(0.1)

    async def receive_transcription(self, websocket):
        try:
            while self.is_streaming:
                transcription_message = await websocket.recv()
                print(f"Received transcription: {transcription_message}")
                
                # Parse the JSON message to extract the transcription text
                try:
                    transcription_dict = json.loads(transcription_message)
                    transcription_text = transcription_dict.get("transcription", "")
                    if transcription_text:
                        # Emit the transcription text (without JSON formatting) to update the UI
                        self.update_transcription.emit(transcription_text)
                    else:
                        print("No transcription found in the message.")
                except json.JSONDecodeError:
                    print(f"Failed to parse transcription message: {transcription_message}")
        except websockets.ConnectionClosed:
            print("WebSocket connection closed")

    def stop(self):
        print("Stopping WebSocket thread...")
        self.is_streaming = False
        if self.websocket and not self.websocket.closed:
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)



class WAVStreamerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.fs = 16000  # Sample rate (16 kHz for WAV format)
        self.chunk_duration = 1  # Send audio in 1-second chunks
        self.buffer = bytearray()  # Buffer to accumulate audio data
        self.chunk_size = self.fs * 2 * 1  # 1 second of audio
        self.audio_queue = Queue()  # Queue for streaming audio data
        self.websocket_thread = None
        self.is_recording = False
        self.audio_stream = None

    def initUI(self):
        # Set window properties
        self.setWindowTitle("Microphone Recorder & Streaming")
        self.setGeometry(100, 100, 300, 500)

        # Create a vertical layout and center its content
        layout = QVBoxLayout()

        # Create a label for instructions and center it
        self.label = QLabel("Click the button to start/stop streaming", self)
        self.label.setAlignment(Qt.AlignCenter)  # Center the label horizontally
        layout.addWidget(self.label)

        # Create a round button with a microphone icon
        self.record_button = QPushButton(self)
        self.record_button.setCheckable(True)  # To toggle between start/stop
        self.record_button.setIcon(QIcon(resource_path("assets/microphone.png")))  # Use your microphone icon PNG
        self.record_button.setIconSize(QSize(50, 50))  # Set icon size (adjust to fit inside the circle)

        # Style for wider gray circle and centered microphone icon
        self.record_button.setStyleSheet("""
            QPushButton {
                border-radius: 75px;  /* Make the button circular */
                background-color: gray;  /* Set the gray background for the circle */
                border: 2px solid gray;  /* Optional: add a border */
            }
            QPushButton:pressed {
                background-color: lightgray;  /* Change color when pressed */
            }
        """)
        self.record_button.setFixedSize(150, 150)  # Set button size for wider circle

        # Center the button
        layout.addWidget(self.record_button, alignment=Qt.AlignCenter)

        # Connect the button click to toggle_recording method
        self.record_button.clicked.connect(self.toggle_recording)

        # Add a QTextEdit for displaying live transcriptions
        self.transcription_area = QTextEdit(self)
        self.transcription_area.setReadOnly(True)  # Make the text area read-only
        layout.addWidget(self.transcription_area)

        # Set the layout to the main window
        self.setLayout(layout)

    def toggle_recording(self):
        if self.record_button.isChecked():
            print("Record button checked, starting streaming")
            self.start_streaming()
        else:
            print("Record button unchecked, stopping streaming")
            self.stop_streaming()

    def start_streaming(self):
        """Start microphone recording and WebSocket streaming."""
        self.label.setText("Streaming... Click again to stop.")
        self.is_recording = True

        # Set up the audio stream
        self.audio_stream = sd.InputStream(samplerate=self.fs, channels=1, dtype='int16',
                                           callback=self.audio_callback)
        self.audio_stream.start()

        # Start WebSocket thread for streaming audio data
        self.websocket_thread = WebSocketThread(f"ws://{TRANSCRIPTION_ENDPOINT.replace("http://", "")}", self.audio_queue)
        self.websocket_thread.update_transcription.connect(self.update_transcription_area)  # Connect signal
        self.websocket_thread.start()

    def stop_streaming(self):
        """Stops WebSocket streaming and closes audio stream."""
        self.label.setText("Streaming stopped.")
        self.is_recording = False

        if self.audio_stream:
            self.audio_stream.stop()

        if self.websocket_thread:
            self.websocket_thread.stop()
            self.websocket_thread.wait()

    def audio_callback(self, indata, frames, time, status):
        """Callback for capturing audio in real-time."""
        if status:
            print(f"Audio stream status: {status}")
    
        max_amplitude = np.max(np.abs(indata))
        print(f"Audio callback received {frames} frames. Max amplitude: {max_amplitude}")
        
        self.buffer.extend(indata.tobytes())

        if len(self.buffer) >= self.chunk_size:
            print(f"Queuing audio chunk of size: {len(self.buffer)}")
            self.audio_queue.put(self.buffer)
            self.buffer = bytearray()  # Clear buffer after sending

    def update_transcription_area(self, transcription):
        """Display transcription results in the text area."""
        self.transcription_area.append(transcription)


# Main function to run the app
def main():
    app = QApplication(sys.argv)
    uploader = WAVStreamerApp()
    uploader.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
