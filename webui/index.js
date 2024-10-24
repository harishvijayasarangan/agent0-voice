import * as msgs from "./messages.js";

const splitter = document.getElementById('splitter');
const leftPanel = document.getElementById('left-panel');
const container = document.querySelector('.container');
const chatInput = document.getElementById('chat-input');
const chatHistory = document.getElementById('chat-history');
const sendButton = document.getElementById('send-button');
const startRecordingButton = document.getElementById('start-recording-button');
const stopRecordingButton = document.getElementById('stop-recording-button');
const inputSection = document.getElementById('input-section');
const statusSection = document.getElementById('status-section');

let isResizing = false;
let autoScroll = true;
let recordingProcess = null;
let isRecording = false;

splitter.addEventListener('mousedown', (e) => {
    isResizing = true;
    document.addEventListener('mousemove', resize);
    document.addEventListener('mouseup', stopResize);
});

function resize(e) {
    if (isResizing) {
        const newWidth = e.clientX - container.offsetLeft;
        leftPanel.style.width = `${newWidth}px`;
    }
}

function stopResize() {
    isResizing = false;
    document.removeEventListener('mousemove', resize);
}

async function startRecording() {
    if (recordingProcess) {
        console.warn("Recording is already in progress.");
        return;
    }

    try {
        console.log("Sending start recording request...");
        const response = await fetch('/start_recording', { method: 'POST' });
        const data = await response.json();
        if (data.ok) {
            recordingProcess = true;
            chatInput.value = "Recording... (Press Stop to stop)";
            chatInput.disabled = true;
            console.log("Recording started.");
        } else {
            console.error("Failed to start recording:", data.message);
        }
    } catch (error) {
        console.error("Error starting recording:", error);
    }
}

async function stopRecording() {
    if (!recordingProcess) {
        console.warn("No recording in progress.");
        return;
    }

    try {
        console.log("Sending stop recording request...");
        const response = await fetch('/stop_recording', { method: 'POST' });
        const data = await response.json();
        if (data.ok) {
            chatInput.value = data.transcription;
            chatInput.disabled = false;
            recordingProcess = null;
            console.log("Recording stopped.");
        } else {
            console.error("Failed to stop recording:", data.message);
        }
    } catch (error) {
        console.error("Error stopping recording:", error);
    }
}

startRecordingButton.addEventListener('click', startRecording);
stopRecordingButton.addEventListener('click', stopRecording);

async function sendMessage() {
    const message = chatInput.value.trim();
    if (message === "") return;

    const messageContainer = document.createElement('div');
    messageContainer.classList.add('message', 'message-user');
    messageContainer.textContent = message;
    chatHistory.appendChild(messageContainer);

    chatInput.value = "";
    chatInput.style.height = 'auto';

    try {
        console.log("Sending message to backend:", message); // Add this line
        const response = await sendJsonData("/msg", { text: message }); // Ensure the endpoint is correct
        if (response.ok) {
            setMessage(response.id, response.type, response.heading, response.content, response.kvps);
        } else {
            console.error("Failed to send message:", response.message);
        }
    } catch (error) {
        console.error("Error sending message:", error);
    }
}

sendButton.addEventListener('click', sendMessage);

chatInput.addEventListener('input', adjustTextareaHeight);

setInterval(poll, 5000); // Poll every 5 seconds

function adjustTextareaHeight() {
    chatInput.style.height = 'auto';
    chatInput.style.height = (chatInput.scrollHeight) + 'px';
}

async function sendJsonData(url, data) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error('Network response was not ok');
    }

    const jsonResponse = await response.json();
    return jsonResponse;
}

let lastLog = 0;
let lastLogVersion = 0;
let lastLogGuid = "";

async function poll() {
    try {
        console.log("Polling for updates..."); // Add this line
        const response = await sendJsonData("/poll", { log_from: lastLog });
        if (response.ok) {
            if (lastLogGuid != response.log_guid) {
                chatHistory.innerHTML = "";
            }

            if (lastLogVersion != response.log_version) {
                for (const log of response.logs) {
                    setMessage(log.no, log.type, log.heading, log.content, log.kvps);
                }
            }

            const inputAD = Alpine.$data(inputSection);
            inputAD.paused = response.paused;
            const statusAD = Alpine.$data(statusSection);
            statusAD.connected = response.ok;

            lastLog = response.log_to;
            lastLogVersion = response.log_version;
            lastLogGuid = response.log_guid;
        } else {
            console.error("Polling failed:", response.message);
            const statusAD = Alpine.$data(statusSection);
            statusAD.connected = false;
        }
    } catch (error) {
        console.error("Error during polling:", error);
        const statusAD = Alpine.$data(statusSection);
        statusAD.connected = false;
    }
}

window.pauseAgent = async function (paused) {
    const resp = await sendJsonData("/pause", { paused: paused });
}

window.resetChat = async function () {
    const resp = await sendJsonData("/reset", {});
}

window.toggleAutoScroll = async function (_autoScroll) {
    autoScroll = _autoScroll;
}

window.toggleJson = async function (showJson) {
    toggleCssProperty('.msg-json', 'display', showJson ? 'block' : 'none');
}

window.toggleThoughts = async function (showThoughts) {
    toggleCssProperty('.msg-thoughts', 'display', showThoughts ? undefined : 'none');
}

function toggleCssProperty(selector, property, value) {
    const styleSheets = document.styleSheets;

    for (let i = 0; i < styleSheets.length; i++) {
        const styleSheet = styleSheets[i];
        const rules = styleSheet.cssRules || styleSheet.rules;

        for (let j = 0; j < rules.length; j++) {
            const rule = rules[j];
            if (rule.selectorText == selector) {
                if (value === undefined) {
                    rule.style.removeProperty(property);
                } else {
                    rule.style.setProperty(property, value);
                }
                return;
            }
        }
    }
}

function setMessage(id, type, heading, content, kvps) {
    const messageContainer = document.createElement('div');
    messageContainer.classList.add('message-container');
    chatHistory.appendChild(messageContainer);

    const handler = msgs.getHandler(type);
    handler(messageContainer, id, type, heading, content, kvps);

    if (autoScroll) {
        messageContainer.scrollIntoView({ behavior: 'smooth' });
    }
}