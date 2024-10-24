from functools import wraps
import os
from pathlib import Path
import threading
from flask import Flask, request, jsonify, Response
from flask_basicauth import BasicAuth
from agent import Agent
from initialize import initialize
from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle
from python.helpers.log import Log
from dotenv import load_dotenv
import subprocess
import signal
import pyaudio
import wave
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

#global agent instance
agent0: Agent|None = None

#initialize the internal Flask server
app = Flask("app",static_folder=get_abs_path("./webui"),static_url_path="/")

# Set up basic authentication, name and password from .env variables
app.config['BASIC_AUTH_USERNAME'] = os.environ.get('BASIC_AUTH_USERNAME') or "admin" #default name
app.config['BASIC_AUTH_PASSWORD'] = os.environ.get('BASIC_AUTH_PASSWORD') or "admin" #default pass
basic_auth = BasicAuth(app)

# get global agent
def get_agent(reset: bool = False) -> Agent:
    global agent0
    if agent0 is None or reset:
        agent0 = initialize()
    return agent0

# Now you can use @requires_auth function decorator to require login on certain pages
def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == app.config['BASIC_AUTH_USERNAME'] and auth.password == app.config['BASIC_AUTH_PASSWORD']):
            return Response(
                'Could not verify your access level for that URL.\n'
                'You have to login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return await f(*args, **kwargs)
    return decorated

# handle default address, show demo html page from ./test_form.html
@app.route('/', methods=['GET'])
async def test_form():
    return Path(get_abs_path("./webui/index.html")).read_text()

# simple health check, just return OK to see the server is running
@app.route('/ok', methods=['GET','POST'])
async def health_check():
    return "OK"

# # secret page, requires authentication
# @app.route('/secret', methods=['GET'])
# @requires_auth
# async def secret_page():
#     return Path("./secret_page.html").read_text()

# send message to agent (async UI)
@app.route('/msg', methods=['POST'])
async def handle_message():
    try:
        # agent instance
        agent = get_agent()

        # data sent to the server
        input = request.get_json()
        text = input.get("text", "")

        # print to console and log
        PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True).print(f"User message:")        
        PrintStyle(font_color="white", padding=False).print(f"> {text}")
        Log.log(type="user", heading="User message", content=text)
        
        # pass the message to the agent
        threading.Thread(target=agent.communicate, args=(text,)).start()
        
        # data from this server    
        response = {
            "ok": True,
            "message": "Message received.",
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }

    # respond with json
    return jsonify(response)

# send message to agent (synchronous API)
@app.route('/msg_sync', methods=['POST'])
async def handle_message_sync():
    try:
        # agent instance
        agent = get_agent()

        # data sent to the server
        input = request.get_json()
        text = input.get("text", "")

        # print to console and log
        PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True).print(f"User message:")        
        PrintStyle(font_color="white", padding=False).print(f"> {text}")
        Log.log(type="user", heading="User message", content=text)
        
        # pass the message to the agent
        response_text = agent.communicate(text)
        
        # data from this server    
        response = {
            "ok": True,
            "message": "Message received.",
            "response": response_text
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }

    # respond with json
    return jsonify(response)

# Web UI polling
@app.route('/poll', methods=['POST'])
async def poll():
    try:
        # data sent to the server
        input = request.get_json()
        from_no = input.get("log_from", "")

        logs = Log.logs[int(from_no):]
        to = Log.last_updated #max(0, len(Log.logs)-1)
        
        # data from this server    
        response = {
            "ok": True,
            "logs": logs,
            "log_to": to,
            "log_guid": Log.guid,
            "log_version": Log.version,
            "paused": Agent.paused
        }

    except Exception as e:
        response = {
            "ok": False,
            "message": str(e),
        }

    # respond with json
    return jsonify(response)

recording = False
recording_thread = None
WAV_FILE = "temp_audio.wav"

def handle_sigint(signum, frame):
    global recording
    recording = False
    print("SIGINT received, stopping recording...")

def record_audio(filename):
    global recording
    recording = True

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    frames = []

    print("Recording started...")
    while recording:
        data = stream.read(1024)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(44100)
    wf.writeframes(b''.join(frames))
    wf.close()
    print("Recording stopped and saved to file.")

def start_recording():
    global recording_thread
    recording_thread = threading.Thread(target=record_audio, args=(WAV_FILE,))
    recording_thread.start()

def stop_recording():
    global recording
    recording = False
    if recording_thread:
        recording_thread.join()

@app.route('/start_recording', methods=['POST'])
def start_recording_route():
    global recording
    if recording:
        return jsonify({"ok": False, "message": "Recording is already in progress."})

    try:
        print("Starting recording process...")
        start_recording()
        return jsonify({"ok": True})
    except Exception as e:
        print(f"Error starting recording process: {e}")
        return jsonify({"ok": False, "message": str(e)})

@app.route('/stop_recording', methods=['POST'])
def stop_recording_route():
    global recording
    if not recording:
        return jsonify({"ok": False, "message": "No recording in progress."})

    try:
        print("Stopping recording process...")
        stop_recording()
        print("Recording process stopped.")

        # Initialize the Groq client with the API key
        
        client = Groq(api_key=os.environ.get("API_KEY_GROQ"))

        # Set the filename to the absolute path of the WAV file
        filename = os.path.abspath(WAV_FILE)

        # Transcribe the audio file
        with open(filename, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filename, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
            transcription_text = transcription.text

        return jsonify({"ok": True, "transcription": transcription_text})
    except Exception as e:
        print(f"Error stopping recording process: {e}")
        return jsonify({"ok": False, "message": str(e)})

#run the internal server
if __name__ == "__main__":

    load_dotenv()
    
    get_agent() #initialize

    # Suppress only request logs but keep the startup messages
    from werkzeug.serving import WSGIRequestHandler
    class NoRequestLoggingWSGIRequestHandler(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            pass  # Override to suppress request logging

    # run the server on port from .env
    port = int(os.environ.get("WEB_UI_PORT", 0)) or None
    app.run(request_handler=NoRequestLoggingWSGIRequestHandler,port=port)