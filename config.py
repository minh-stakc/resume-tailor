import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root if it exists

# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"

# Pipeline thresholds
PROJECT_RELEVANCE_THRESHOLD = 6   # out of 10; projects below this are replaced
MIN_PROJECTS = 3
MAX_PROJECTS = 3
MAX_EXPERIENCES = 4
MAX_BULLETS_PER_EXPERIENCE = 3
MAX_BULLETS_PER_PROJECT = 2

# Retry config
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# pdflatex binary (auto-detected, can override with PDFLATEX env var)
PDFLATEX = os.environ.get(
    "PDFLATEX",
    r"C:\Users\hoang\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe",
)

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
JOBS_DIR = os.path.join(os.path.dirname(__file__), "jobs")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
MASTER_RESUME = os.path.join(DATA_DIR, "master_resume.json")
APPLICANT_PROFILE = os.path.join(DATA_DIR, "applicant_profile.json")
RESUME_TEMPLATE = os.path.join(TEMPLATES_DIR, "resume.tex.j2")

# Playwright / browser automation
PLAYWRIGHT_HEADLESS = False   # always headful for user review
PLAYWRIGHT_SLOW_MO = 100      # ms delay between actions for stability
BROWSER_TIMEOUT = 30000        # ms timeout for page loads
