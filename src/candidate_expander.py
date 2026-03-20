"""Step 2: Expand JD signals using Claude's knowledge of successful candidates for this role type."""

import json
import re
import sys
import time

import anthropic
import config

SYSTEM = """You are a senior technical recruiter with deep knowledge of what successful candidates actually look like for any given role — not just what the JD says, but what their resumes and LinkedIn profiles consistently show.
Return ONLY valid JSON — no markdown, no explanation."""

PROMPT = """A job description has been analyzed. Now expand the candidate signal beyond what the JD explicitly states.

Role type: {role_type}
Ideal candidate (from JD): {ideal_candidate_narrative}
Core problems (from JD): {key_problems}
JD-stated primary skills: {primary_skills}
JD domain terms: {domain_keywords}

Based on your knowledge of what candidates who successfully land this type of role show on their resumes and LinkedIn profiles — beyond what any single JD says — provide:

1. Additional technical skills, tools, and frameworks that commonly appear in strong candidates' profiles for this role (that may not be explicitly mentioned in the JD above)
2. Additional domain terms, jargon, and buzzwords used in this field that signal deep familiarity
3. Patterns of experience that distinguish strong candidates — specific types of work they have shipped or contributed to (e.g., "built and owned end-to-end ML training pipelines", "contributed to open-source inference tooling", "shipped latency-sensitive backend services at scale")
4. What separates top-10% candidates from average ones for this role — be specific and concrete

Return JSON:
{{
  "expanded_skills": ["<5-10 additional skill/tool/framework strings>"],
  "expanded_domain_keywords": ["<5-10 additional domain term strings>"],
  "typical_experience_patterns": ["<3-5 concrete experience pattern strings>"],
  "candidate_differentiators": ["<2-4 concrete differentiator strings>"]
}}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def _dedup(lst: list) -> list:
    """Deduplicate a list case-insensitively, preserving original casing of first occurrence."""
    seen = set()
    result = []
    for item in lst:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def expand_candidate_signals(jd_analysis: dict) -> dict:
    """
    Enrich jd_analysis with candidate signals beyond the raw JD text.
    Merges expanded_skills into secondary_skills, expanded_domain_keywords into domain_keywords,
    and adds typical_experience_patterns and candidate_differentiators as new keys.
    Returns the enriched jd_analysis dict (mutated in-place and returned).
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    key_problems = jd_analysis.get("key_problems", [])
    prompt = PROMPT.format(
        role_type=jd_analysis.get("role_type", ""),
        ideal_candidate_narrative=jd_analysis.get("ideal_candidate_narrative", ""),
        key_problems="\n".join(f"- {p}" for p in key_problems) if key_problems else "(not specified)",
        primary_skills=", ".join(jd_analysis.get("primary_skills", [])),
        domain_keywords=", ".join(jd_analysis.get("domain_keywords", [])),
    )

    for attempt in range(config.MAX_RETRIES):
        try:
            print("[2/6] Expanding candidate signals...", file=sys.stderr)
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=1024,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            expanded = _parse_json(response.content[0].text)

            # Merge into jd_analysis
            jd_analysis["secondary_skills"] = _dedup(
                jd_analysis.get("secondary_skills", []) + expanded.get("expanded_skills", [])
            )
            jd_analysis["domain_keywords"] = _dedup(
                jd_analysis.get("domain_keywords", []) + expanded.get("expanded_domain_keywords", [])
            )
            jd_analysis["typical_experience_patterns"] = expanded.get("typical_experience_patterns", [])
            jd_analysis["candidate_differentiators"] = expanded.get("candidate_differentiators", [])
            return jd_analysis

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] Candidate expansion attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)
        except anthropic.APIError as e:
            print(f"[WARN] API error on attempt {attempt+1}: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)

    # Fallback: return jd_analysis unchanged, with empty new keys
    print("[WARN] Candidate signal expansion failed. Continuing with JD-only signals.", file=sys.stderr)
    jd_analysis.setdefault("typical_experience_patterns", [])
    jd_analysis.setdefault("candidate_differentiators", [])
    return jd_analysis
