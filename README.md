# Resume Tailor

AI-powered resume customization CLI that tailors your master resume to any job description using Claude.

## What It Does

Paste a job description and get a professionally tailored, 1-page resume PDF in seconds. The pipeline:

1. **Parses the JD** — extracts role type, required skills, framing angle, and target class year
2. **Expands candidate signals** — Claude infers additional keywords and experience patterns that strong candidates for this role typically have
3. **Scores & selects projects** — ranks your projects by relevance; fills gaps with AI-generated ones grounded in your actual skill set
4. **Rewrites bullets** — reframes experience bullets using JD vocabulary, domain language, and framing angle
5. **Ranks skills** — surfaces the most relevant skills for the role
6. **Renders & enforces 1 page** — compiles with pdflatex, trims bullets/entries until it fits, then fills back to maximize page density

Outputs two university-variant resumes per job (`output/<job_name>/stanford.pdf`, `output/<job_name>/uf.pdf`).

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:
```
ANTHROPIC_API_KEY=your_key_here
PDFLATEX=/path/to/pdflatex   # optional, auto-detected on most systems
```

pdflatex must be installed — [MiKTeX](https://miktex.org/) on Windows, TeX Live on Linux/Mac.

## Usage

```bash
# Paste a job description interactively (saves to jobs/<name>.txt)
python main.py tailor --paste <job_name> --compile

# Use an existing job description file
python main.py tailor --job jobs/example.txt --output output/example.tex --compile

# Generate only one university variant
python main.py tailor --paste <job_name> --compile --university stanford
```

## Stack

- **[Claude API](https://anthropic.com)** (`claude-sonnet-4-6`) — JD analysis, signal expansion, project generation, bullet rewriting, skill ranking
- **Jinja2** — LaTeX template rendering
- **pdflatex** — PDF compilation and 1-page enforcement loop
