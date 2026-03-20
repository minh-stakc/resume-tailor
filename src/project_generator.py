"""Step 3: Generate new projects when fewer than MIN_PROJECTS real ones qualify."""

import json
import re
import sys
import time

import anthropic
import config

SYSTEM = """You are a resume strategist generating realistic project descriptions for a student's resume.
Projects must be specific, technically credible, achievable by one person in 1-3 months, and strategically chosen to reinforce the candidate's fit for the target role.
Return ONLY valid JSON — no markdown, no explanation."""

PROMPT = """Generate {n} new resume projects for a student applying to this role.

Target Role:
- Type: {role_type}
- Ideal candidate: {ideal_candidate_narrative}
- Core problems this role must solve: {key_problems}
- Key skills needed: {primary_skills}
- Domain terms: {domain_keywords}

CRITICAL CONSTRAINT — The student's ACTUAL skill set (ONLY use technologies from this list):
Languages: {languages}
Frameworks: {frameworks}
Infrastructure: {infrastructure}
Backend: {backend}

Do NOT use any technology not listed above. This is non-negotiable.

Already selected projects (do not repeat these concepts or tech combos):
{selected_names}

Generate {n} project(s). Each project must:
- Directly demonstrate solving one of the role's core problems OR prove the ideal candidate narrative
- Use at least 2 technologies from the student's actual skill list above
- Include exactly 3 bullet points with plausible, realistic metrics for a solo 1-3 month project
- Have quantified results (e.g., "reduced X by Y%", "processed Z records", "improved N by M%")
- Sound like something a top CS undergrad at a research university would build
- Project name must be SHORT — 5 words or fewer (e.g., "Options Pricing Engine", "MEV Arbitrage Simulator")
- Each bullet follows strict format: Action Verb + what you built/did + measurable result. Max 1 printed line (~120 characters). No narrative tails or justification phrases after the result.

Return JSON:
{{
  "projects": [
    {{
      "id": "generated_001",
      "name": "<project name>",
      "tech": ["<tech1>", "<tech2>", "<tech3>"],
      "start": "Jan 2025",
      "end": "May 2025",
      "bullets": [
        "<bullet 1 with metric>",
        "<bullet 2 with metric>",
        "<bullet 3 with metric>"
      ],
      "tags": ["<tag1>", "<tag2>"],
      "generated": true
    }}
  ]
}}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def generate_projects(n: int, jd_analysis: dict, master_skills: dict, selected_projects: list) -> list:
    """Generate n new projects grounded in the candidate's real skills."""
    if n <= 0:
        return []

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    selected_names = [p["name"] for p in selected_projects]

    key_problems = jd_analysis.get("key_problems", [])
    prompt = PROMPT.format(
        n=n,
        role_type=jd_analysis["role_type"],
        ideal_candidate_narrative=jd_analysis.get("ideal_candidate_narrative", ""),
        key_problems="\n".join(f"- {p}" for p in key_problems) if key_problems else "(not specified)",
        primary_skills=", ".join(jd_analysis.get("primary_skills", [])),
        domain_keywords=", ".join(jd_analysis.get("domain_keywords", [])),
        languages=", ".join(master_skills.get("languages", [])),
        frameworks=", ".join(master_skills.get("frameworks", [])),
        infrastructure=", ".join(master_skills.get("infrastructure", [])),
        backend=", ".join(master_skills.get("backend", [])),
        selected_names=", ".join(selected_names) if selected_names else "none",
    )

    for attempt in range(config.MAX_RETRIES):
        try:
            print(f"[4/6] Generating {n} new project(s)...", file=sys.stderr)
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=2000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            result = _parse_json(response.content[0].text)
            projects = result["projects"]
            # Assign sequential IDs and mark as generated
            for i, p in enumerate(projects):
                p["id"] = f"generated_{i+1:03d}"
                p["generated"] = True
                p.setdefault("score", 10)
            return projects[:n]

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] Project generation attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)
        except anthropic.APIError as e:
            print(f"[WARN] API error on attempt {attempt+1}: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)

    print("[WARN] Project generation failed. No new projects added.", file=sys.stderr)
    return []
