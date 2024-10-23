from http.server import BaseHTTPRequestHandler, HTTPServer
import cgi
import torch
import whisper
import json
import os
import deepl
from dotenv import load_dotenv
load_dotenv()

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", None)
translator = deepl.Translator(DEEPL_API_KEY)

# Load Whisper model on GPU (use GPU 3 if available)
#device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
#model = whisper.load_model("turbo", device=device)
model = whisper.load_model("turbo")

class TranscriptionHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        # Only accept POST requests with multipart/form-data
        if 'multipart/form-data' in self.headers['Content-Type']:
            try:
                # Parse the multipart form-data to get the uploaded file
                form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
                file_field = form['file']  # Assuming the file field is named 'file'

                if file_field.filename:
                    # Save the uploaded MP3 file temporarily
                    file_data = file_field.file.read()
                    temp_filename = "temp_audio.mp3"
                    with open(temp_filename, "wb") as f:
                        f.write(file_data)

                    # Transcribe the audio using Whisper
                    result = model.transcribe(temp_filename, language='de', task='translate')
                    transcription = result['text']

                    # Clean up the temp file
                    os.remove(temp_filename)

                    # Respond with the transcription
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    translation = translator.translate_text(transcription, target_lang="EN-GB")
                    response = {"transcription": translation.text}
                    self.wfile.write(json.dumps(response).encode())
                else:
                    # File field was missing or empty
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing file in request.")
            except Exception as e:
                # Handle unexpected errors
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Internal Server Error: {str(e)}".encode())
        else:
            # If the request doesn't contain multipart/form-data, return 400
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid content-type. Expected multipart/form-data.")

# Set up server
server_address = ('0.0.0.0', 42331)
httpd = HTTPServer(server_address, TranscriptionHandler)
print("Server started at port 42331...")
httpd.serve_forever()