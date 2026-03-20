"""Loads and merges master_resume + applicant_profile into a unified dict for form filling."""

import json
import os

import config


def load_applicant_info(university: str, master_path: str = None, profile_path: str = None) -> dict:
    """Return a flat dict with all info needed to fill an application form.

    Args:
        university: "stanford" or "uf"
        master_path: path to master_resume.json (default from config)
        profile_path: path to applicant_profile.json (default from config)
    """
    master_path = master_path or config.MASTER_RESUME
    profile_path = profile_path or config.APPLICANT_PROFILE

    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)

    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    # Use variant-specific meta/education
    variant = master.get("variants", {}).get(university, {})
    meta = variant.get("meta", master["meta"])
    education = variant.get("education", master["education"])

    # Split name
    name_parts = meta["name"].split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    # Build linkedin URL (ensure https://)
    linkedin_raw = meta.get("linkedin", "")
    linkedin_url = ""
    if linkedin_raw:
        linkedin_url = linkedin_raw if linkedin_raw.startswith("http") else f"https://{linkedin_raw}"

    github_raw = meta.get("github", "")
    github_url = ""
    if github_raw:
        github_url = github_raw if github_raw.startswith("http") else f"https://{github_raw}"

    info = {
        # Personal
        "first_name": profile.get("legal_first_name", first_name),
        "last_name": profile.get("legal_last_name", last_name),
        "preferred_name": profile.get("preferred_name", first_name),
        "full_name": meta["name"],
        "email": meta["email"],
        "phone": meta["phone"],
        "linkedin": linkedin_url,
        "github": github_url,

        # Address
        "street": profile.get("address", {}).get("street", ""),
        "city": profile.get("address", {}).get("city", ""),
        "state": profile.get("address", {}).get("state", ""),
        "zip": profile.get("address", {}).get("zip", ""),
        "country": profile.get("address", {}).get("country", "United States"),

        # Education
        "school": education["institution"],
        "degree": education["degree"],
        "gpa": education["gpa"],
        "graduation": education["graduation"],

        # Work authorization
        "work_authorization": profile.get("work_authorization", True),
        "requires_sponsorship": profile.get("requires_sponsorship", False),

        # Demographics (optional EEO fields)
        "gender": profile.get("gender", ""),
        "race_ethnicity": profile.get("race_ethnicity", ""),
        "veteran_status": profile.get("veteran_status", False),
        "disability_status": profile.get("disability_status", False),

        # Misc
        "how_did_you_hear": profile.get("how_did_you_hear", ""),
        "custom_answers": profile.get("custom_answers", {}),
    }

    return info
