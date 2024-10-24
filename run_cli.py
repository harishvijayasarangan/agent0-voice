from dotenv import load_dotenv
load_dotenv()

import threading, time, os  # models is imported but not used yet
from ansio import application_keypad, mouse_input, raw_input
from ansio.input import InputEvent, get_input_event
from agent import Agent, AgentConfig
from python.helpers.print_style import PrintStyle
from python.helpers.files import read_file
from python.helpers import files
import python.helpers.timed_input as timed_input
from initialize import initialize
from colorama import Fore, Back, Style
import colorama

input_lock = threading.Lock()
os.chdir(files.get_abs_path("./work_dir")) #change CWD to work_dir

# Main conversation loop
def chat(agent:Agent):
    colorama.init()
    full_sentences = []
    displayed_text = ""
    
    def clear_console():
        os.system('clear' if os.name == 'posix' else 'cls')

    def text_detected(text):
        nonlocal displayed_text
        sentences_with_style = [
            f"{Fore.YELLOW + sentence + Style.RESET_ALL if i % 2 == 0 else Fore.CYAN + sentence + Style.RESET_ALL} "
            for i, sentence in enumerate(full_sentences)
        ]
        new_text = "".join(sentences_with_style).strip() + " " + text if len(sentences_with_style) > 0 else text

        if new_text != displayed_text:
            displayed_text = new_text
            clear_console()
            print(displayed_text, end="", flush=True)

    def process_transcription(text):
        full_sentences.append(text)
        text_detected("")
        return text

    while True:
        # ask user for message
        with input_lock:
            timeout = agent.get_data("timeout")
            if not timeout:
                PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True).print(f"User message ('a' for audio, 'e' to leave):")        
                import readline
                user_input = input("> ")
                PrintStyle(font_color="white", padding=False, log_only=True).print(f"> {user_input}") 
            else:
                PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True).print(f"User message ({timeout}s timeout, 'w' to wait, 'a' for audio, 'e' to leave):")        
                import readline
                user_input = timeout_input("> ", timeout=timeout)
                
                if not user_input:
                    user_input = agent.read_prompt("fw.msg_timeout.md")
                    PrintStyle(font_color="white", padding=False).stream(f"{user_input}")        
                else:
                    user_input = user_input.strip()
                    if user_input.lower() == "w":
                        user_input = input("> ").strip()
                    PrintStyle(font_color="white", padding=False, log_only=True).print(f"> {user_input}")        

        if user_input.lower() == 'e':
            break
        elif user_input.lower() == 'a':
            clear_console()
            print("Voice functionality not available.")
            continue

        if user_input:
            assistant_response = agent.message_loop(user_input)
        else:
            continue
        
        PrintStyle(font_color="white",background_color="#1D8348", bold=True, padding=True).print(f"{agent.agent_name}: response:")        
        PrintStyle(font_color="white").print(f"{assistant_response}")        

# User intervention during agent streaming
def intervention():
    if Agent.streaming_agent and not Agent.paused:
        Agent.paused = True # stop agent streaming
        PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True).print(f"User intervention ('e' to leave, empty to continue):")        

        import readline # this fixes arrow keys in terminal
        user_input = input("> ").strip()
        PrintStyle(font_color="white", padding=False, log_only=True).print(f"> {user_input}")        
        
        if user_input.lower() == 'e': os._exit(0) # exit the conversation when the user types 'exit'
        if user_input: Agent.streaming_agent.intervention_message = user_input # set intervention message if non-empty
        Agent.paused = False # continue agent streaming 

# Capture keyboard input to trigger user intervention
def capture_keys():
    global input_lock
    intervent=False            
    while True:
        if intervent: intervention()
        intervent = False
        time.sleep(0.1)
        
        if Agent.streaming_agent:
            with input_lock, raw_input, application_keypad:
                event: InputEvent | None = get_input_event(timeout=0.1)
                if event and (event.shortcut.isalpha() or event.shortcut.isspace()):
                    intervent=True
                    continue

# User input with timeout
def timeout_input(prompt, timeout=10):
    return timed_input.timeout_input(prompt=prompt, timeout=timeout)

if __name__ == "__main__":
    print("Initializing framework...")

    # Start the key capture thread for user intervention during agent streaming
    threading.Thread(target=capture_keys, daemon=True).start()

    # initialize and start the chat
    agent0 = initialize()
    chat(agent0)
