#!/usr/bin/env python3
"""Quick test to verify OpenAI API key is working."""

import sys
from pathlib import Path

try:
    import openai
except ImportError:
    print("ERROR: openai package not installed")
    sys.exit(1)

# Load API key
api_key_file = Path(__file__).parent / "api_key.txt"
if not api_key_file.exists():
    print(f"ERROR: API key file not found at {api_key_file}")
    sys.exit(1)

with open(api_key_file) as f:
    api_key = f.read().strip()

if not api_key:
    print("ERROR: API key file is empty")
    sys.exit(1)

print(f"OpenAI version: {openai.__version__}")
print(f"API key loaded (length: {len(api_key)})")
print("Testing API call...")

try:
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'API test successful' if you can read this."}
        ],
        max_tokens=20,
        request_timeout=10
    )
    
    result = response.choices[0].message["content"].strip()
    print(f"SUCCESS: API call worked!")
    print(f"Response: {result}")
    
except Exception as e:
    print(f"ERROR: API call failed")
    print(f"Exception: {type(e).__name__}: {e}")
    sys.exit(1)
