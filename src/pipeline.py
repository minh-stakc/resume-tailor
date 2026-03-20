"""Orchestrates the full resume tailoring pipeline."""

import sys
from copy import deepcopy
from datetime import date

import config
from src.jd_parser import parse_jd
from src.candidate_expander import expand_candidate_signals
from src.project_scorer import score_projects
from src.project_generator import generate_projects
from src.bullet_rewriter import rewrite_bullets
from src.skill_ranker import rank_skills
from src.renderer import render


def _graduation_year_for(target_class_year: str) -> str | None:
    """Return 'May YYYY' for the given class year relative to today, or None for 'any'."""
    today = date.today()
    senior_year = today.year if today.month < 8 else today.year + 1
    offsets = {"senior": 0, "new_grad": 0, "junior": 1, "sophomore": 2, "freshman": 3}
    offset = offsets.get(target_class_year)
    return f"May {senior_year + offset}" if offset is not None else None


class TailorPipeline:
    def __init__(self, master_resume: dict, jd_text: str, threshold: int = None, university: str = None):
        self.master = master_resume
        self.jd_text = jd_text
        self.threshold = threshold or config.PROJECT_RELEVANCE_THRESHOLD
        self.university = university  # "stanford", "uf", or None (include all)

        self.ctx: dict = {}
        self._render_context: dict = {}
        self._last_added_item: dict | None = None  # for undo_last_add()

    def run(self) -> str:
        """Execute all pipeline steps and return the rendered LaTeX string."""
        # Step 1: Parse JD
        self.ctx["jd_analysis"] = parse_jd(self.jd_text)

        # Step 2: Expand candidate signals
        self.ctx["jd_analysis"] = expand_candidate_signals(self.ctx["jd_analysis"])

        # Step 3: Score projects
        scored_projects = score_projects(
            deepcopy(self.master["projects"]),
            self.ctx["jd_analysis"],
            self.threshold,
        )
        self.ctx["scored_projects"] = scored_projects

        # Cap to MAX_PROJECTS — projects are sorted by score desc, so this keeps the top ones
        selected = [p for p in scored_projects if p.get("keep", False)][:config.MAX_PROJECTS]
        self.ctx["selected_projects"] = selected

        # Step 4: Generate projects if needed
        n_needed = config.MIN_PROJECTS - len(selected)
        generated = []
        if n_needed > 0:
            generated = generate_projects(
                n=n_needed,
                jd_analysis=self.ctx["jd_analysis"],
                master_skills=self.master["skills"],
                selected_projects=selected,
            )
        self.ctx["generated_projects"] = generated
        self.ctx["final_projects"] = selected + generated

        # Step 5: Select and rewrite experiences
        experiences = self._select_experiences()
        rewritten_exps = rewrite_bullets(experiences, self.ctx["jd_analysis"])
        self.ctx["experiences"] = rewritten_exps

        # Step 6: Rank skills
        ranked_skills = rank_skills(self.master["skills"], self.ctx["jd_analysis"])
        self.ctx["ranked_skills"] = ranked_skills

        print("[6/6] Rendering LaTeX...", file=sys.stderr)
        self._render_context = self._build_render_context()
        return render(self._render_context)

    def _select_experiences(self) -> list:
        exps = deepcopy(self.master["experiences"])

        # Filter by university — exclude experiences tagged to the other institution
        if self.university == "stanford":
            exps = [e for e in exps if e.get("university") != "uf"]
        elif self.university == "uf":
            exps = [e for e in exps if e.get("university") != "stanford"]

        jd = self.ctx["jd_analysis"]
        jd_terms = set()
        for field in ("primary_skills", "secondary_skills", "domain_keywords"):
            jd_terms.update(t.lower() for t in jd.get(field, []))

        def overlap_score(exp):
            tags = {t.lower() for t in exp.get("tags", [])}
            score = 0
            for tag in tags:
                for jt in jd_terms:
                    if tag == jt or tag in jt or jt in tag:
                        score += 1
                        break
            return score

        for exp in exps:
            exp["_overlap"] = overlap_score(exp)

        most_recent = exps[0]
        rest = sorted(exps[1:], key=lambda e: e["_overlap"], reverse=True)

        # Cap to MAX_EXPERIENCES: always keep most recent, take top N-1 by relevance
        rest = rest[:max(config.MAX_EXPERIENCES - 1, 0)]
        selected = [most_recent] + rest

        original_order = {exp["id"]: i for i, exp in enumerate(exps)}
        selected.sort(key=lambda e: original_order[e["id"]])
        return selected

    def _build_render_context(self) -> dict:
        """Build the render context. Stores _all_bullets for fill/trim loops."""
        projects_for_template = []
        for p in self.ctx["final_projects"]:
            bullets = p.get("bullets", [])
            if bullets and isinstance(bullets[0], dict):
                bullets = [b["text"] for b in bullets]
            all_bullets = list(bullets)
            shown = list(all_bullets)  # start with all — overshoot, then trim
            projects_for_template.append({
                "name": p["name"],
                "tech_string": ", ".join(p.get("tech", [])),
                "start": p.get("start", ""),
                "end": p.get("end", "Present"),
                "bullets": shown,
                "_all_bullets": all_bullets,
                "generated": p.get("generated", False),
                "_id": p["id"],
            })

        experiences_for_template = []
        for exp in self.ctx["experiences"]:
            bullets = exp.get("bullets", [])
            if bullets and isinstance(bullets[0], dict):
                bullets = [b["text"] for b in bullets]
            all_bullets = list(bullets)
            shown = list(all_bullets)  # start with all — overshoot, then trim
            experiences_for_template.append({
                "company": exp["company"],
                "location": exp["location"],
                "title": exp["title"],
                "start": exp["start"],
                "end": exp.get("end", "Present"),
                "bullets": shown,
                "_all_bullets": all_bullets,
                "_id": exp["id"],
                "_overlap": exp.get("_overlap", 0),
            })

        variant = self.master.get("variants", {}).get(self.university, {})
        meta = variant.get("meta", self.master["meta"])
        education = variant.get("education", self.master["education"])

        grad_override = _graduation_year_for(self.ctx["jd_analysis"].get("target_class_year", "any"))
        if grad_override:
            education = dict(education)
            education["graduation"] = grad_override

        skills = self.ctx["ranked_skills"]
        return {
            "meta": meta,
            "education": education,
            "experiences": experiences_for_template,
            "projects": projects_for_template,
            "skills": {
                "languages_str": ", ".join(skills.get("languages", [])),
                "frameworks_str": ", ".join(skills.get("frameworks", [])),
                "backend_str": ", ".join(skills.get("backend", [])),
                "infrastructure_str": ", ".join(skills.get("infrastructure", [])),
                "competitions_str": ", ".join(skills.get("competitions", [])),
            },
        }

    def add_one_bullet(self) -> str | None:
        """
        Add the next unused bullet to the first item that has reserve bullets.
        Priority: experiences (most recent first), then projects.
        Returns new LaTeX string, or None if no reserve bullets remain.
        """
        items = (
            self._render_context.get("experiences", [])
            + self._render_context.get("projects", [])
        )
        for item in items:
            shown = item["bullets"]
            reserve = item.get("_all_bullets", shown)
            if len(shown) < len(reserve):
                item["bullets"] = shown + [reserve[len(shown)]]
                self._last_added_item = item
                label = item.get("company") or item.get("name", "?")
                print(f"[FILL] Added bullet to '{label}' ({len(item['bullets'])}/{len(reserve)})", file=sys.stderr)
                return render(self._render_context)
        return None  # no reserve bullets left

    def undo_last_add(self) -> str:
        """Remove the bullet that was just added by add_one_bullet()."""
        if self._last_added_item and len(self._last_added_item["bullets"]) > 0:
            self._last_added_item["bullets"].pop()
            self._last_added_item = None
        return render(self._render_context)

    def trim_one_bullet(self) -> tuple[str, bool]:
        """
        Remove the last bullet from the lowest-relevance item that has > 1 bullet.
        Works from the end of experiences backward, then projects.
        Returns (tex, trimmed) where trimmed=False means nothing could be removed.
        """
        items = (
            list(reversed(self._render_context.get("experiences", [])))
            + list(reversed(self._render_context.get("projects", [])))
        )
        for item in items:
            if len(item["bullets"]) > 1:
                item["bullets"].pop()
                label = item.get("company") or item.get("name", "?")
                print(f"[TRIM] Removed bullet from '{label}' ({len(item['bullets'])} left)", file=sys.stderr)
                return render(self._render_context), True

        return render(self._render_context), False

    def trim_one_entry(self) -> tuple[str, bool]:
        """
        Remove an entire experience or project entry when all bullets are at minimum.
        Experiences: removes the least-relevant one (by _overlap), always keeping the most recent.
        Projects: removes the last (least-relevant by score).
        Returns (tex, trimmed) where trimmed=False means nothing could be removed.
        """
        exps = self._render_context.get("experiences", [])
        if len(exps) > 1:
            # Never remove index 0 (most recent); remove least-relevant from the rest
            least = min(exps[1:], key=lambda e: e.get("_overlap", 0))
            exps.remove(least)
            print(f"[TRIM] Removed experience entry '{least.get('company', '?')}'", file=sys.stderr)
            return render(self._render_context), True

        projs = self._render_context.get("projects", [])
        if len(projs) > 1:
            removed = projs.pop()
            print(f"[TRIM] Removed project entry '{removed.get('name', '?')}'", file=sys.stderr)
            return render(self._render_context), True

        print("[WARN] Cannot trim further — at minimum entries.", file=sys.stderr)
        return render(self._render_context), False
