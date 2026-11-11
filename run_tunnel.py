import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(BASE_DIR, "app.py")
CLOUDFLARED = os.path.join(BASE_DIR, "cloudflared.exe")
URL_FILE = os.path.join(BASE_DIR, "tunnel_url.txt")

if not os.path.exists(CLOUDFLARED):
    print(f"Error: {CLOUDFLARED} not found.")
    sys.exit(1)

print("Starting Flask application...")
app_proc = subprocess.Popen([sys.executable, APP_PATH], cwd=BASE_DIR)

# Wait for local server to respond
print("Waiting for server to start on http://127.0.0.1:5000 ...")
ready = False
for _ in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/", timeout=1) as resp:
            if resp.status == 200:
                ready = True
                break
    except Exception:
        time.sleep(0.5)

if not ready:
    print("Flask server failed to respond in time.")
    app_proc.terminate()
    sys.exit(1)

print("Flask server is running!")
print("Starting Cloudflare Tunnel...")

cf_proc = subprocess.Popen(
    [CLOUDFLARED, "tunnel", "--url", "http://127.0.0.1:5000", "--no-autoupdate"],
    cwd=BASE_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

tunnel_url = None
url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

def cleanup(*_):
    print("\nStopping processes...")
    try:
        cf_proc.terminate()
    except Exception:
        pass
    try:
        app_proc.terminate()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# Read cloudflared output line by line
try:
    for line in cf_proc.stdout:
        match = url_regex.search(line)
        if match and not tunnel_url:
            tunnel_url = match.group(0)
            with open(URL_FILE, "w", encoding="utf-8") as f:
                f.write(tunnel_url + "\n")
            print("=" * 60)
            print(f"LIVE SHAREABLE LINK: {tunnel_url}")
            print("=" * 60)
            sys.stdout.flush()
        if "ERR" in line:
            print(f"[cloudflared error] {line.strip()}", flush=True)
except KeyboardInterrupt:
    cleanup()

