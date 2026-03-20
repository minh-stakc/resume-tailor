#!/usr/bin/env python3
"""Resume Tailor CLI — tailor your resume to any job description using Claude AI."""

import argparse
import json
import os
import re
import subprocess
import sys

import config
from src.pipeline import TailorPipeline


def load_master_resume(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_job_description(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def paste_job_description(name: str) -> tuple[str, str, str]:
    """
    Prompt the user to paste a JD. Saves it to jobs/<name>.txt.
    Returns (jd_text, job_path, output_path).
    """
    job_path = os.path.join(config.JOBS_DIR, f"{name}.txt")
    output_path = os.path.join(config.OUTPUT_DIR, f"{name}.tex")

    print(f"Job: {name}")
    print(f"  Will save JD  → jobs/{name}.txt")
    print(f"  Will output   → output/{name}.tex")
    print()
    print("Paste the job description below.")
    print("When done, press Ctrl+Z then Enter (Windows) or Ctrl+D (Mac/Linux).")
    print("-" * 60)
    lines = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass
    text = "\n".join(lines).strip()
    if not text:
        print("[ERROR] No job description provided.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(config.JOBS_DIR, exist_ok=True)
    with open(job_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[OK] Saved JD to: {job_path}", file=sys.stderr)

    return text, job_path, output_path


def compile_latex(tex_path: str) -> int:
    """
    Run pdflatex on the .tex file.
    Returns page count on success, or 0 on failure.
    Reads page count from the .log file pdflatex always writes — more reliable than stdout parsing.
    """
    out_dir = os.path.dirname(tex_path)
    result = subprocess.run(
        [config.PDFLATEX, "-interaction=nonstopmode", f"-output-directory={out_dir}", tex_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("[ERROR] pdflatex failed:", file=sys.stderr)
        print(result.stdout[-2000:], file=sys.stderr)
        return 0

    # pdflatex always writes a .log file — parse it for the definitive page count
    log_path = os.path.join(out_dir, os.path.splitext(os.path.basename(tex_path))[0] + ".log")
    sources = [result.stdout, result.stderr]
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            sources.append(f.read())
    except OSError:
        pass

    # MiKTeX on Windows wraps lines at 80 chars, so "Output written on ... (2\n pages"
    # spans two lines — search the full text with re.DOTALL to handle the line break.
    for text in sources:
        m = re.search(r"Output written on .+?\((\d+)", text, re.DOTALL)
        if m:
            pages = int(m.group(1))
            print(f"[pages] detected {pages} page(s)", file=sys.stderr)
            return pages

    print("[WARN] Could not detect page count — defaulting to 2 to force trim.", file=sys.stderr)
    return 2  # conservative: assume overflow so the trim loop always runs


def run_single(master, jd_text, output_path, threshold, compile_flag, university):
    """Run the full pipeline for one university variant and write output."""
    print(f"\n[*] Generating {university.upper()} resume → {output_path}", file=sys.stderr)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    pipeline = TailorPipeline(
        master_resume=master,
        jd_text=jd_text,
        threshold=threshold,
        university=university,
    )
    tex_content = pipeline.run()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tex_content)
    print(f"[OK] LaTeX written to: {output_path}", file=sys.stderr)

    if compile_flag:
        abs_output = os.path.abspath(output_path)
        pdf_path = abs_output.replace(".tex", ".pdf")

        def write_and_compile(tex: str) -> int:
            with open(abs_output, "w", encoding="utf-8") as f:
                f.write(tex)
            pages = compile_latex(abs_output)
            if pages == 0:
                sys.exit(1)
            return pages

        print("[*] Compiling with pdflatex...", file=sys.stderr)
        pages = write_and_compile(tex_content)

        # Phase 1: trim until 1 page (bullets first, then entire entries)
        if pages > 1:
            print(f"[*] {pages} pages — trimming to 1 page...", file=sys.stderr)
            for _ in range(100):
                tex_content, trimmed = pipeline.trim_one_bullet()
                if not trimmed:
                    tex_content, trimmed = pipeline.trim_one_entry()
                    if not trimmed:
                        print("[WARN] Cannot trim further.", file=sys.stderr)
                        break
                pages = write_and_compile(tex_content)
                if pages <= 1:
                    break

        # Phase 2: fill — keep adding bullets as long as it stays on 1 page
        if pages == 1:
            print("[*] Filling page...", file=sys.stderr)
            for _ in range(30):
                candidate = pipeline.add_one_bullet()
                if candidate is None:
                    print("[*] No more reserve bullets — page is maximally filled.", file=sys.stderr)
                    break
                new_pages = write_and_compile(candidate)
                if new_pages > 1:
                    tex_content = pipeline.undo_last_add()
                    write_and_compile(tex_content)
                    print("[*] Page is full — stopped filling.", file=sys.stderr)
                    break
                tex_content = candidate

        print(f"[OK] PDF written to: {pdf_path}", file=sys.stderr)


def cmd_tailor(args):
    if not config.ANTHROPIC_API_KEY:
        print("[ERROR] ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # Load inputs
    master = load_master_resume(args.resume)
    if args.paste:
        jd_text, _, base_output = paste_job_description(args.paste)
    else:
        jd_text = load_job_description(args.job)
        base_output = args.output

    # Determine which university variants to generate
    universities = ["stanford", "uf"] if args.university == "both" else [args.university]

    # Always place outputs in output/<job_name>/<university>.tex
    base_dir = os.path.dirname(os.path.abspath(base_output))
    job_name = os.path.splitext(os.path.basename(base_output))[0]

    for uni in universities:
        output_path = os.path.join(base_dir, job_name, f"{uni}.tex")
        run_single(master, jd_text, output_path, args.threshold, args.compile, uni)


def cmd_apply(args):
    """Scrape JD from URL, tailor resume, and auto-fill the application form."""
    if not config.ANTHROPIC_API_KEY:
        print("[ERROR] ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    from urllib.parse import urlparse
    from src.scraper import open_job_page
    from src.ats import detect_ats
    from src.applicant import load_applicant_info
    from src.form_filler import fill_application

    url = args.url

    # Derive job name from URL if not provided
    if args.name:
        job_name = args.name
    else:
        parsed = urlparse(url)
        # Use last meaningful path segment as job name
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        job_name = path_parts[-1] if path_parts else "job"
        job_name = re.sub(r"[^a-zA-Z0-9_-]", "_", job_name)

    university = args.university

    # Step 1: Detect ATS platform
    adapter = detect_ats(url)

    # Step 2: Open page and scrape JD
    print(f"[*] Opening {url}")
    jd_text, page, context, browser = open_job_page(url)

    # Use adapter's JD extraction if available (more targeted)
    adapter_jd = adapter.extract_jd(page)
    if len(adapter_jd) > 200:
        jd_text = adapter_jd

    # Save JD
    os.makedirs(config.JOBS_DIR, exist_ok=True)
    job_path = os.path.join(config.JOBS_DIR, f"{job_name}.txt")
    with open(job_path, "w", encoding="utf-8") as f:
        f.write(jd_text)
    print(f"[OK] Saved JD to: {job_path}")

    # Step 3: Tailor resume and compile PDF
    master = load_master_resume(args.resume)
    output_path = os.path.join(config.OUTPUT_DIR, job_name, f"{university}.tex")
    run_single(master, jd_text, output_path, args.threshold, True, university)

    pdf_path = os.path.abspath(output_path.replace(".tex", ".pdf"))
    if not os.path.exists(pdf_path):
        print("[ERROR] PDF was not generated. Cannot fill application.", file=sys.stderr)
        context.close()
        browser.close()
        sys.exit(1)

    # Step 4: Load applicant info
    applicant_info = load_applicant_info(university, master_path=args.resume)

    # Step 5: Fill application form
    fill_application(page, context, browser, adapter, applicant_info, pdf_path)


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered resume tailor using Claude."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- tailor command ---
    tailor = sub.add_parser("tailor", help="Tailor resume to a job description")
    jd_source = tailor.add_mutually_exclusive_group(required=True)
    jd_source.add_argument("--job", help="Path to job description file (or - for stdin)")
    jd_source.add_argument("--paste", metavar="NAME", help="Paste JD interactively; saves to jobs/NAME.txt and outputs to output/NAME.tex")
    tailor.add_argument("--output", help="Output .tex file path (required when using --job, auto-set when using --paste)")
    tailor.add_argument("--resume", default=config.MASTER_RESUME, help="Path to master_resume.json")
    tailor.add_argument("--threshold", type=int, default=config.PROJECT_RELEVANCE_THRESHOLD,
                        help="Project relevance threshold 1-10 (default: 6)")
    tailor.add_argument("--compile", action="store_true", help="Run pdflatex after generating .tex")
    tailor.add_argument("--university", choices=["stanford", "uf", "both"], default="both",
                        help="Which university variant to generate (default: both)")

    # --- apply command ---
    apply_cmd = sub.add_parser("apply", help="Scrape JD from URL, tailor resume, and auto-fill application form")
    apply_cmd.add_argument("--url", required=True, help="URL of the job posting")
    apply_cmd.add_argument("--name", help="Job name for output files (auto-derived from URL if omitted)")
    apply_cmd.add_argument("--university", choices=["stanford", "uf"], required=True,
                           help="University variant to use (required — you apply as one identity)")
    apply_cmd.add_argument("--resume", default=config.MASTER_RESUME, help="Path to master_resume.json")
    apply_cmd.add_argument("--threshold", type=int, default=config.PROJECT_RELEVANCE_THRESHOLD,
                           help="Project relevance threshold 1-10 (default: 6)")

    args = parser.parse_args()
    if args.command == "tailor":
        if args.job and not args.output:
            parser.error("--output is required when using --job")
        cmd_tailor(args)
    elif args.command == "apply":
        cmd_apply(args)


if __name__ == "__main__":
    main()
