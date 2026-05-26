import requests
import json

def test_ollama():
    url = "http://localhost:11434/api/generate"
    
    # We'll use a very small prompt to test
    payload = {
        "model": "gemma4",
        "prompt": "You are a pilot logbook assistant. Respond with 'READY' if you can hear me.",
        "stream": False
    }
    
    print("Connecting to your Mac Mini's AI (Ollama)...")
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print(f"Success! AI Response: {result.get('response')}")
        else:
            print(f"Error: Ollama returned status {response.status_code}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Check if the Ollama app is running in your menu bar.")

if __name__ == "__main__":
    test_ollama()
