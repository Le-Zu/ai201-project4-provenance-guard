import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_PATH = os.getenv("DATABASE_PATH", "provenance_guard.db")
LLM_MODEL = "llama-3.3-70b-versatile"
