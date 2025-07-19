from dotenv import load_dotenv
import os

load_dotenv()

print("✔️ ENV Loaded")
print("HUGGINGFACE_API_KEY:", os.getenv("HUGGINGFACE_API_KEY"))
