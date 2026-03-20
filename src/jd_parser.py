"""Step 1: Parse a job description into structured signals for downstream steps."""

import json
import re
import sys
import time

import anthropic
import config

SYSTEM = """You are a senior technical recruiter and resume strategist. Extract structured information from job descriptions with precision, including the narrative intelligence needed to position a candidate as the perfect hire.
Return ONLY valid JSON — no markdown, no explanation."""

PROMPT = """Analyze this job description and extract structured information.

Job Description:
{jd_text}

Return a JSON object with exactly these fields:
{{
  "role_type": "one of: ML Engineer | Quant | Backend SWE | Frontend SWE | Full Stack SWE | DevOps/Cloud | Research | Data Engineer | Data Scientist | Robotics | Security | Other",
  "seniority": "one of: intern | junior | mid | senior",
  "primary_skills": ["list of 5-10 must-have technical skills, tools, or frameworks explicitly mentioned"],
  "secondary_skills": ["list of 3-7 nice-to-have or implied skills"],
  "domain_keywords": ["list of 5-10 domain/industry terms like 'low-latency', 'distributed systems', 'real-time', 'financial modeling'"],
  "action_verbs": ["list of 5-8 strong action verbs used or implied by the role, e.g. 'design', 'optimize', 'deploy', 'architect'"],
  "culture_signals": ["list of 2-4 culture/environment signals like 'fast-paced', 'research-oriented', 'production systems'"],
  "ideal_candidate_narrative": "2-3 sentences describing the ideal hire: their background, the kind of work they have already done, and why they would thrive in this specific role.",
  "key_problems": ["3-5 specific technical or business challenges this role is hired to solve — be concrete, not generic"],
  "framing_angle": "Exactly one sentence: the strategic lens through which ALL candidate experience should be reframed. E.g. 'Frame all ML and systems work as production reliability infrastructure, not research.' or 'Emphasize quantitative rigor and financial modeling depth over general engineering scale.'",
  "target_class_year": "one of: freshman | sophomore | junior | senior | new_grad | any — infer from explicit graduation year requirements, class standing mentions ('rising junior', 'sophomore summer'), specific class year programs, or 'new grad'/'entry level' language. Default to 'any' if unclear."
}}"""


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def parse_jd(jd_text: str) -> dict:
    """Extract structured signals from a job description. Returns a dict."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    for attempt in range(config.MAX_RETRIES):
        try:
            print("[1/6] Analyzing job description...", file=sys.stderr)
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=1024,
                system=SYSTEM,
                messages=[{"role": "user", "content": PROMPT.format(jd_text=jd_text)}],
            )
            result = _parse_json(response.content[0].text)
            # Ensure required fields exist with defaults
            result.setdefault("role_type", "Other")
            result.setdefault("seniority", "junior")
            result.setdefault("primary_skills", [])
            result.setdefault("secondary_skills", [])
            result.setdefault("domain_keywords", [])
            result.setdefault("action_verbs", ["develop", "build", "implement", "design", "optimize"])
            result.setdefault("culture_signals", [])
            result.setdefault("ideal_candidate_narrative", "")
            result.setdefault("key_problems", [])
            result.setdefault("framing_angle", "")
            result.setdefault("target_class_year", "any")
            return result
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] JD parse attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)
        except anthropic.APIError as e:
            print(f"[WARN] API error on attempt {attempt+1}: {e}", file=sys.stderr)
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_DELAY)

    # Fallback: return minimal structure
    print("[WARN] JD parsing failed after retries. Using empty analysis.", file=sys.stderr)
    return {
        "role_type": "Other",
        "seniority": "junior",
        "primary_skills": [],
        "secondary_skills": [],
        "domain_keywords": [],
        "action_verbs": ["develop", "build", "implement"],
        "culture_signals": [],
        "ideal_candidate_narrative": "",
        "key_problems": [],
        "framing_angle": "",
        "target_class_year": "any",
    }
