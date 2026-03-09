import os

from dotenv import load_dotenv
from yaml import safe_load


load_dotenv()

RESULTS_DIR = os.getenv("RESULTS_DIR")
IMAGE_DIR = os.getenv("IMAGE_DIR")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
CONFIG_PATH = os.getenv("CONFIG_PATH")
NUM_WORKERS = int(os.getenv("NUM_WORKERS", os.cpu_count()))

print(f"RESULTS_DIR: {RESULTS_DIR}")
print(f"IMAGE_DIR: {IMAGE_DIR}")
print(f"LLM_BASE_URL: {LLM_BASE_URL}")
print(f"MODEL_NAME: {MODEL_NAME}")
with open(CONFIG_PATH, "r") as f:
    CONFIG = safe_load(f)
