import json
import os

# Adjust paths as needed
data_dir = "data"
for filename in os.listdir(data_dir):
    if filename.endswith(".json"):
        print(f"Checking {filename}...")
        with open(os.path.join(data_dir, filename), 'r') as f:
            data = json.load(f)
            history = data.get('history', [])
            if not history:
                print("  History is empty!")
            else:
                print(f"  History has {len(history)} entries.")
                print("  Sample keys:", history[0].keys())
                print("  Sample entry:", history[0])
