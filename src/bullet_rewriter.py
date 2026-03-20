"""Step 4: Rewrite experience bullets to match JD language and keywords."""

import json
import re
import sys
import time

import anthropic
import config

SYSTEM = """You are a concise technical resume writer. Every bullet follows one strict format: Action Verb + What You Did / Context + Measurable Result. Bullets are dense with signal, never padded with justification. Numbers and metrics must never change.
Return ONLY valid JSON — no markdown, no explanation."""

PROMPT = """Rewrite this candidate's experience bullets to position them as the perfect hire for this role.

TARGET ROLE INTELLIGENCE:
- Role: {role_type}
- Ideal candidate: {ideal_candidate_narrative}
- Core problems this role must solve: {key_problems}
- Framing angle: {framing_angle}
- Keywords to weave in naturally: {primary_skills}
- Domain language: {domain_keywords}
- Preferred action verbs: {action_verbs}
- What strong candidates for this role typically have done: {typical_experience_patterns}
- What separates top candidates from average ones: {candidate_differentiators}

REWRITING STRATEGY:
1. Apply the framing angle by choosing WHICH aspect of the work to lead with and WHAT WORDS to use — not by adding explanatory text after the result.
2. Within each experience, put the bullet most relevant to this role FIRST.
3. Use JD vocabulary and domain language naturally inside the bullet itself — not as appended justification.

BULLET FORMAT — every bullet must follow this structure:
  [Strong Action Verb] + [what you built/did + key context] + [measurable result]
  Example: "Engineered distributed backtesting pipeline across 500+ strategy configs, reducing research cycle time by 35%."
  Target length: 1 printed line. Hard max: 2 printed lines (~120–140 characters).

STRICT RULES — never violate these:
1. NEVER change any number, percentage, or metric. Reproduce them character-for-character (e.g., "35%", "20M+", "15+", "84% IoU").
2. Do not invent new metrics, projects, or technologies not present in the original bullet.
3. Do not add tools or frameworks the original bullet does not mention.
4. Keep bullet count exactly the same.
5. Every bullet must begin with a strong action verb.
6. NEVER append narrative justification tails. The following patterns are strictly banned — cut them entirely:
   - "— demonstrating the ability to..."
   - "— reflecting..."
   - "— illustrating..."
   - "— showing..."
   - "— enabling the capacity to..."
   - "— highlighting..."
   - any phrase starting with "—" that explains WHY the result matters
   If a bullet ends with a metric or concrete outcome, stop there. The result speaks for itself.

Experiences to rewrite:
{experiences_json}

Return JSON:
{{
  "rewritten": [
    {{
      "id": "<experience id>",
      "bullets": ["<rewritten bullet 1>", "<rewritten bullet 2>", ...]
    }}
  ]
}}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def _has_tag_overlap(exp_tags: list, jd_primary: list, jd_domain: list) -> bool:
    """Check if an experience has any overlap with JD keywords."""
    jd_terms = {t.lower() for t in jd_primary + jd_domain}
    exp_terms = {t.lower() for t in exp_tags}
    # Also check partial matches
    for et in exp_terms:
        for jt in jd_terms:
            if et in jt or jt in et:
                return True
    return False


def rewrite_bullets(experiences: list, jd_analysis: dict) -> list:
    """
    Rewrite bullets for experiences that overlap with JD keywords.
    Returns updated experiences list with rewritten bullets.
    """
    primary = jd_analysis.get("primary_skills", [])
    domain = jd_analysis.get("domain_keywords", [])
    action_verbs = jd_analysis.get("action_verbs", [])

    # Split into experiences to rewrite vs. pass-through
    to_rewrite = []
    passthrough = []
    for exp in experiences:
        if _has_tag_overlap(exp.get("tags", []), primary, domain):
            to_rewrite.append(exp)
        else:
            passthrough.append(exp)

    if not to_rewrite:
        return experiences

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build slim version for prompt
    slim_exps = []
    for exp in to_rewrite:
        bullets = exp.get("bullets", [])
        # bullets may be list of dicts {id, text, tags} or list of strings
        if bullets and isinstance(bullets[0], dict):
            bullet_texts = [b["text"] for b in bullets]
        else:
            bullet_texts = bullets
        slim_exps.append({
            "id": exp["id"],
            "company": exp["company"],
            "title": exp["title"],
            "bullets": bullet_texts,
        })

    key_problems = jd_analysis.get("key_problems", [])
    typical_patterns = jd_analysis.get("typical_experience_patterns", [])
    differentiators = jd_analysis.get("candidate_differentiators", [])
    prompt = PROMPT.format(
        role_type=jd_analysis["role_type"],
        ideal_candidate_narrative=jd_analysis.get("ideal_candidate_narrative", ""),
        key_problems="\n".join(f"- {p}" for p in key_problems) if key_problems else "(not specified)",
        framing_angle=jd_analysis.get("framing_angle", ""),
        primary_skills=", ".join(primary),
        action_verbs=", ".join(action_verbs),
        domain_keywords=", ".join(domain),
        typical_experience_patterns="\n".join(f"- {p}" for p in typical_patterns) if typical_patterns else "(not specified)",
        candidate_differentiators="\n".join(f"- {p}" for p in differentiators) if differentiators else "(not specified)",
        experiences_json=json.dumps(slim_exps, indent=2),
    )

    for attempt in range(config.MAX_RETRIES):
        try:
            print("[5/6] Rewriting experience bullets...", file=sys.stderr)
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=3000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            result = _parse_json(response.content[0].text)
            rewritten_by_id = {r["id"]: r["bullets"] for r in result["rewritten"]}

            # Merge rewritten bullets back
            updated = []
            for exp in experiences:
                exp = dict(exp)
                if exp["id"] in rewritten_by_id:
                    exp["bullets"] = rewritten_by_id[exp["id"]]
                else:
                    # Pass-through: flatten bullets to plain strings
                    raw = exp.get("bullets", [])
                    if raw and isinstance(raw[0], dict):
                        exp["bullets"] = [b["text"] for b in raw]
                updated.append(exp)
            return updated

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] Bullet rewrite attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)
        except anthropic.APIError as e:
            print(f"[WARN] API error on attempt {attempt+1}: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)

    # Fallback: flatten bullet dicts to strings, return unchanged
    print("[WARN] Bullet rewriting failed. Using original bullets.", file=sys.stderr)
    result = []
    for exp in experiences:
        exp = dict(exp)
        raw = exp.get("bullets", [])
        if raw and isinstance(raw[0], dict):
            exp["bullets"] = [b["text"] for b in raw]
        result.append(exp)
    return result
