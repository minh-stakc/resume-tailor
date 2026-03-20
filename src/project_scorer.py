"""Step 2: Score existing projects for relevance to the job description."""

import json
import re
import sys
import time

import anthropic
import config

SYSTEM = """You are a senior technical recruiter scoring resume projects for narrative fit and relevance to a specific role.
Score based on both technical match AND how well the project proves the candidate can solve this role's core problems.
Return ONLY valid JSON — no markdown, no explanation."""

PROMPT = """Score each candidate project for relevance to this job.

Job Analysis:
- Role type: {role_type}
- Ideal candidate: {ideal_candidate_narrative}
- Core problems this role must solve: {key_problems}
- Primary skills required: {primary_skills}
- Domain keywords: {domain_keywords}

Candidate Projects:
{projects_json}

For each project, assign a score 1-10 based on BOTH technical match AND narrative fit:
- 8-10: Strong fit — uses required skills AND directly demonstrates solving the role's core problems or proves the ideal candidate narrative
- 5-7: Partial fit — overlaps some skills or domain, or shows adjacent relevant capability
- 1-4: Weak fit — different tech stack, unrelated domain, or does not reinforce the candidate's story for this role

Return JSON:
{{
  "scores": [
    {{
      "id": "<project id>",
      "score": <integer 1-10>,
      "rationale": "<one sentence explaining technical AND narrative fit>",
      "keep": <true if score >= {threshold}>
    }}
  ]
}}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def score_projects(projects: list, jd_analysis: dict, threshold: int) -> list:
    """
    Score all projects against the JD. Returns the projects list with added
    'score', 'rationale', and 'keep' fields, sorted by score descending.
    """
    if not projects:
        return []

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Send only the fields Claude needs for scoring
    slim_projects = [
        {
            "id": p["id"],
            "name": p["name"],
            "tech": p["tech"],
            "tags": p["tags"],
            "bullets": p["bullets"][:2],  # first 2 bullets for context
        }
        for p in projects
    ]

    key_problems = jd_analysis.get("key_problems", [])
    prompt = PROMPT.format(
        role_type=jd_analysis["role_type"],
        ideal_candidate_narrative=jd_analysis.get("ideal_candidate_narrative", ""),
        key_problems="\n".join(f"- {p}" for p in key_problems) if key_problems else "(not specified)",
        primary_skills=", ".join(jd_analysis["primary_skills"]),
        domain_keywords=", ".join(jd_analysis["domain_keywords"]),
        projects_json=json.dumps(slim_projects, indent=2),
        threshold=threshold,
    )

    for attempt in range(config.MAX_RETRIES):
        try:
            print("[3/6] Scoring projects...", file=sys.stderr)
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=1024,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            result = _parse_json(response.content[0].text)
            scores_by_id = {s["id"]: s for s in result["scores"]}

            # Merge scores back into project objects
            scored = []
            for p in projects:
                p = dict(p)
                sc = scores_by_id.get(p["id"], {"score": 0, "rationale": "not scored", "keep": False})
                p["score"] = sc.get("score", 0)
                p["rationale"] = sc.get("rationale", "")
                p["keep"] = p["score"] >= threshold
                scored.append(p)

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] Project scoring attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)
        except anthropic.APIError as e:
            print(f"[WARN] API error on attempt {attempt+1}: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)

    # Fallback: include all projects with score 0
    print("[WARN] Project scoring failed. Including all projects.", file=sys.stderr)
    for p in projects:
        p["score"] = 5
        p["keep"] = True
        p["rationale"] = "fallback"
    return projects
