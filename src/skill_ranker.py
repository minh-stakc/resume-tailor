"""Step 5: Reorder skills to front-load JD-relevant ones. No API call needed."""


def rank_skills(skills: dict, jd_analysis: dict) -> dict:
    """
    Reorder each skill category so JD-relevant skills appear first.
    Returns a new skills dict with the same categories but reordered lists.
    """
    # Build relevance set (lowercased)
    primary = {s.lower() for s in jd_analysis.get("primary_skills", [])}
    secondary = {s.lower() for s in jd_analysis.get("secondary_skills", [])}
    domain = {s.lower() for s in jd_analysis.get("domain_keywords", [])}

    def score_skill(skill: str) -> int:
        s = skill.lower()
        if s in primary:
            return 3
        if s in secondary:
            return 2
        if s in domain:
            return 1
        # Partial match: check if any keyword is a substring of the skill
        for kw in primary:
            if kw in s or s in kw:
                return 2
        for kw in secondary | domain:
            if kw in s or s in kw:
                return 1
        return 0

    ranked = {}
    for category, skill_list in skills.items():
        if not isinstance(skill_list, list):
            ranked[category] = skill_list
            continue
        ranked[category] = sorted(skill_list, key=lambda s: -score_skill(s))

    return ranked
