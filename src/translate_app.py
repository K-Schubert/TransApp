import sys
import sounddevice as sd
import numpy as np
import wave
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import QSize, Qt, QThread
from pydub import AudioSegment
import requests
import os
from dotenv import load_dotenv
load_dotenv()

TRANSCRIPTION_ENDPOINT = os.environ.get("TRANSCRIPTION_ENDPOINT", None)

class RecordThread(QThread):
    def __init__(self, parent=None, fs=44100):
        super().__init__(parent)
        self.fs = fs
        self.is_recording = False
        self.recording_data = None
        self.duration = 60  # Maximum recording duration in seconds

    def run(self):
        """Starts recording audio in a separate thread."""
        self.is_recording = True
        self.recording_data = sd.rec(int(self.duration * self.fs), samplerate=self.fs, channels=1, dtype='int16')
        sd.wait()  # Blocking wait inside the thread

    def stop(self):
        """Stops the recording."""
        if self.is_recording:
            sd.stop()
            self.is_recording = False


class MP3UploaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.fs = 44100  # Sample rate (44.1 kHz)
        self.record_thread = None
        self.wav_file = "recorded_audio.wav"

    def initUI(self):
        # Set window properties
        self.setWindowTitle("Microphone Recorder & Transcription")
        self.setGeometry(100, 100, 200, 400)  # Adjust window size as needed

        # Create a vertical layout and center its content
        layout = QVBoxLayout()

        # Create a label for instructions and center it
        self.label = QLabel("Click the button to start/stop recording", self)
        self.label.setAlignment(Qt.AlignCenter)  # Center the label horizontally
        layout.addWidget(self.label)

        # Create a round button with a microphone icon
        self.record_button = QPushButton(self)
        self.record_button.setCheckable(True)  # To toggle between start/stop
        self.record_button.setIcon(QIcon("assets/microphone.png"))  # Use your microphone icon PNG
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
        layout.addWidget(self.record_button, alignment=Qt.AlignCenter)  # Center the button horizontally

        # Connect the button click to toggle_recording method
        self.record_button.clicked.connect(self.toggle_recording)

        # Set the layout to the main window
        self.setLayout(layout)

    def toggle_recording(self):
        """Starts or stops recording based on the toggle state of the button."""
        if self.record_button.isChecked():
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        """Starts recording audio from the microphone in a separate thread."""
        self.label.setText("Recording... Click again to stop.")
        self.record_thread = RecordThread(fs=self.fs)
        self.record_thread.start()  # Start the recording in the background

    def stop_recording(self):
        """Stops recording and processes the audio."""
        self.label.setText("Recording stopped. Processing audio...")

        # Stop the recording
        if self.record_thread:
            self.record_thread.stop()
            self.record_thread.wait()  # Ensure the thread has finished

            # Save the recording to a WAV file
            self.save_wav_file(self.wav_file, self.record_thread.recording_data)

            # Convert to MP3
            mp3_file = self.convert_wav_to_mp3(self.wav_file)

            # Upload and transcribe the MP3 file
            self.upload_and_transcribe(mp3_file)

            # Clean up files
            os.remove(self.wav_file)
            os.remove(mp3_file)

    def save_wav_file(self, file_name, recording):
        """Saves the recorded audio to a WAV file."""
        with wave.open(file_name, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes per sample
            wf.setframerate(self.fs)
            wf.writeframes(recording.tobytes())

    def convert_wav_to_mp3(self, wav_file):
        """Converts the recorded WAV file to MP3 using PyDub and FFmpeg."""
        mp3_file = "recorded_audio.mp3"
        audio = AudioSegment.from_wav(wav_file)
        audio.export(mp3_file, format="mp3")
        return mp3_file

    def upload_and_transcribe(self, mp3_file):
        """Uploads the MP3 file and sends a POST request to the transcription endpoint."""
        try:
            # Display message that the request is in progress
            self.show_message("Uploading", "Uploading MP3 and waiting for transcription...")

            # Send POST request with the MP3 file
            files = {'file': open(mp3_file, 'rb')}
            response = requests.post(TRANSCRIPTION_ENDPOINT, files=files)

            if response.status_code == 200:
                transcription_result = response.json().get("transcription", "No transcription found.")
                # Show the transcription result
                self.show_message("Transcription", transcription_result)
            else:
                self.show_message("Error", f"Failed to transcribe: {response.status_code}")
        except Exception as e:
            self.show_message("Error", f"An error occurred: {str(e)}")

    def show_message(self, title, message):
        """Displays a message box with a title and message."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

# Main function to run the app
def main():
    app = QApplication(sys.argv)
    uploader = MP3UploaderApp()
    uploader.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
