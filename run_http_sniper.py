import os
import sys
import time
import subprocess
import logging
import yaml
from pyngrok import ngrok, conf
from dotenv import set_key, load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NgrokRunner")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
NGROK_CONFIG_PATH = os.path.join(PROJECT_ROOT, "ngrok.yml")

logger.info("Starting Flask Sniper...")
flask_proc = subprocess.Popen([sys.executable, "flask_sniper.py"], cwd=PROJECT_ROOT)
time.sleep(2)

logger.info("Configuring ngrok with API Key...")
token = os.getenv("NGROK_AUTHTOKEN")

if token:
    # Generate ngrok.yml as per https://ngrok.com/docs/agent/config/v3#api_key
    config = {
        "version": "3",
        "agent": {
            "authtoken": token,
            "api_key": token
        }
    }
    with open(NGROK_CONFIG_PATH, "w") as f:
        yaml.dump(config, f)
    
    # Configure pyngrok to use this config file
    pyngrok_config = conf.PyngrokConfig(config_path=NGROK_CONFIG_PATH)
    public_url = ngrok.connect(5000, pyngrok_config=pyngrok_config).public_url
    logger.info(f"Ngrok Tunnel active: {public_url}")
else:
    logger.warning("No NGROK_AUTHTOKEN found. Falling back to localhost.")
    public_url = "http://localhost:5000"

env_path = os.path.join(PROJECT_ROOT, ".env")
set_key(env_path, "SNIPER_HTTP_URL", public_url)
logger.info(f"Saved SNIPER_HTTP_URL to .env: {public_url}")

try:
    while True: time.sleep(10)
except KeyboardInterrupt:
    logger.info("Shutting down...")
    ngrok.kill()
    flask_proc.terminate()
    if os.path.exists(NGROK_CONFIG_PATH): os.remove(NGROK_CONFIG_PATH)
