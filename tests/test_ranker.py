from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.ranker import (
    classify_role,
    company_score,
    detect_early_career,
    detect_visa_signal,
    is_senior_role,
    matched_skills,
    parse_max_experience,
    recency_score,
    role_score,
    score_job,
    skill_score,
    visa_score,
)


# ── detect_visa_signal ────────────────────────────────────────────────────────

class TestDetectVisaSignal:
    def test_positive_sponsor_phrase(self):
        assert detect_visa_signal("We will sponsor H-1B visas for qualified candidates.") == 1

    def test_negative_no_sponsor(self):
        assert detect_visa_signal("Applicants must be authorized to work without sponsorship.") == -1

    def test_unknown_no_keywords(self):
        assert detect_visa_signal("Looking for experienced software engineers.") == 0

    def test_empty_string(self):
        assert detect_visa_signal("") == 0

    def test_none_description(self):
        assert detect_visa_signal(None) == 0

    def test_negative_checked_before_positive(self):
        # Both phrases present — negative is checked first, must return -1
        desc = "We cannot sponsor. We welcome H-1B candidates to apply."
        assert detect_visa_signal(desc) == -1


# ── classify_role ─────────────────────────────────────────────────────────────

class TestClassifyRole:
    def test_ml_from_title(self):
        assert classify_role("Machine Learning Engineer", "") == "ml"

    def test_backend_from_title(self):
        # "backend engineer" is the exact keyword; "Backend Software Engineer" matches
        # "software engineer" (fullstack) first because fullstack keywords are checked last
        # but the role keyword for backend is "backend engineer" — use that exact phrase
        assert classify_role("Backend Engineer", "") == "backend"

    def test_network_from_title(self):
        assert classify_role("Network Engineer", "") == "network"

    def test_data_scientist_from_title(self):
        assert classify_role("Data Scientist", "") == "ds"

    def test_cloud_from_title(self):
        assert classify_role("Cloud Infrastructure Engineer", "") == "cloud"

    def test_frontend_from_title(self):
        assert classify_role("Frontend Developer", "") == "frontend"

    def test_title_takes_priority_over_description(self):
        # Title says ml — even if desc mentions backend, ml wins
        assert classify_role("ML Engineer", "backend APIs and services") == "ml"

    def test_falls_back_to_description(self):
        # Title "Engineer" matches no role keyword, so classification falls back to description
        role = classify_role("Engineer", "Looking for a backend engineer with Python experience")
        assert role == "backend"

    def test_empty_returns_other(self):
        assert classify_role("", "") == "other"

    def test_no_match_returns_other(self):
        assert classify_role("Administrative Coordinator", "manage calendars") == "other"


# ── detect_early_career ───────────────────────────────────────────────────────

class TestDetectEarlyCareer:
    def test_new_grad_in_title(self):
        assert detect_early_career("New Grad Software Engineer", "") == 1

    def test_entry_level_in_title(self):
        assert detect_early_career("Entry Level Developer", "") == 1

    def test_junior_in_title(self):
        assert detect_early_career("Junior Software Engineer", "") == 1

    def test_early_career_in_description(self):
        assert detect_early_career("Software Engineer", "This is an entry-level position.") == 1

    def test_senior_not_early_career(self):
        assert detect_early_career("Senior Software Engineer", "5+ years required") == 0

    def test_empty_inputs(self):
        assert detect_early_career("", "") == 0


# ── parse_max_experience ──────────────────────────────────────────────────────

class TestParseMaxExperience:
    def test_single_mention(self):
        assert parse_max_experience("3+ years of experience required") == 3

    def test_returns_max_of_multiple(self):
        assert parse_max_experience("2 years preferred, 5 years of experience ideal") == 5

    def test_no_mention_returns_none(self):
        assert parse_max_experience("Looking for skilled engineers") is None

    def test_empty_returns_none(self):
        assert parse_max_experience("") is None

    def test_none_returns_none(self):
        assert parse_max_experience(None) is None

    def test_large_number(self):
        assert parse_max_experience("10 years of experience required") == 10


# ── skill_score ───────────────────────────────────────────────────────────────

class TestSkillScore:
    def test_empty_string(self):
        assert skill_score("") == 0.0

    def test_none(self):
        assert skill_score(None) == 0.0

    def test_no_matching_skills(self):
        assert skill_score("We seek great problem solvers with passion.") == 0.0

    def test_single_skill_positive(self):
        assert skill_score("Must know Python programming.") > 0.0

    def test_many_skills_capped_at_one(self):
        desc = (
            "python java javascript typescript golang react nodejs django flask "
            "aws kubernetes docker pytorch tensorflow scikit-learn postgresql "
            "mongodb redis git kafka grafana prometheus"
        )
        assert skill_score(desc) == 1.0

    def test_score_bounded(self):
        s = skill_score("Experience with Python and AWS.")
        assert 0.0 <= s <= 1.0


# ── recency_score ─────────────────────────────────────────────────────────────

class TestRecencyScore:
    def _days_ago(self, n: int) -> str:
        return (date.today() - timedelta(days=n)).isoformat()

    def test_today(self):
        assert recency_score(date.today().isoformat()) == 1.00

    def test_one_day_old(self):
        assert recency_score(self._days_ago(1)) == 0.90

    def test_three_days_old(self):
        assert recency_score(self._days_ago(3)) == 0.80

    def test_seven_days_old(self):
        assert recency_score(self._days_ago(7)) == 0.60

    def test_fourteen_days_old(self):
        assert recency_score(self._days_ago(14)) == 0.35

    def test_thirty_days_old(self):
        assert recency_score(self._days_ago(30)) == 0.15

    def test_none_returns_default(self):
        assert recency_score(None) == 0.3

    def test_invalid_date_returns_default(self):
        assert recency_score("not-a-date") == 0.3


# ── company_score ─────────────────────────────────────────────────────────────

class TestCompanyScore:
    def test_tier1_fintech_capped_at_one(self):
        # 1.0 + 0.10 would exceed 1.0 — should be capped
        assert company_score(1, "fintech") == 1.0

    def test_tier1_tech_capped_at_one(self):
        assert company_score(1, "tech") == 1.0

    def test_tier2_tech(self):
        assert company_score(2, "tech") == pytest.approx(0.70)  # 0.65 + 0.05

    def test_tier2_enterprise_no_bonus(self):
        assert company_score(2, "enterprise") == pytest.approx(0.65)

    def test_tier3_tech(self):
        assert company_score(3, "tech") == pytest.approx(0.40)  # 0.35 + 0.05

    def test_unknown_tier_uses_default(self):
        assert company_score(99, "tech") == pytest.approx(0.40)  # 0.35 + 0.05

    def test_unknown_industry_no_bonus(self):
        assert company_score(2, "unknown_industry") == pytest.approx(0.65)


# ── is_senior_role ────────────────────────────────────────────────────────────

class TestIsSeniorRole:
    def test_senior_in_title(self):
        assert is_senior_role("Senior Software Engineer", "", None) is True

    def test_staff_in_title(self):
        assert is_senior_role("Staff Engineer", "", None) is True

    def test_principal_in_title(self):
        assert is_senior_role("Principal Engineer", "", None) is True

    def test_lead_in_title(self):
        assert is_senior_role("Tech Lead", "", None) is True

    def test_new_grad_title_not_senior(self):
        assert is_senior_role("New Grad Software Engineer", "", None) is False

    def test_high_exp_years_is_senior(self):
        assert is_senior_role("Software Engineer", "", 5) is True

    def test_three_years_threshold(self):
        assert is_senior_role("Software Engineer", "", 3) is True

    def test_two_years_not_senior(self):
        assert is_senior_role("Software Engineer", "", 2) is False

    def test_none_exp_not_senior(self):
        assert is_senior_role("Software Engineer", "", None) is False

    def test_high_exp_with_early_career_desc_not_senior(self):
        # exp_years_max=5 but description says entry-level → not senior
        assert is_senior_role("Software Engineer", "This is an entry-level new grad role.", 5) is False


# ── role_score ────────────────────────────────────────────────────────────────

class TestRoleScore:
    def test_backend_highest(self):
        assert role_score("backend") == 1.00

    def test_cloud_second(self):
        assert role_score("cloud") == 0.90

    def test_other_lowest(self):
        assert role_score("other") == 0.20

    def test_unknown_category_defaults_to_other(self):
        assert role_score("unicorn") == 0.20


# ── visa_score ────────────────────────────────────────────────────────────────

class TestVisaScore:
    def test_confirmed(self):
        assert visa_score(1) == 1.0

    def test_no_sponsor(self):
        assert visa_score(-1) == 0.0

    def test_unknown(self):
        assert visa_score(0) == 0.4


# ── score_job ─────────────────────────────────────────────────────────────────

class TestScoreJob:
    def _base_job(self, **overrides) -> dict:
        job = {
            "title": "Software Engineer",
            "description": "python backend developer",
            "role_category": "backend",
            "visa_signal": 1,
            "posted_date": date.today().isoformat(),
            "tier": 1,
            "industry": "tech",
            "exp_years_max": None,
        }
        job.update(overrides)
        return job

    def test_returns_all_expected_keys(self):
        result = score_job(self._base_job())
        assert set(result.keys()) == {
            "skill_score", "role_score", "visa_score",
            "recency_score", "company_score", "total_score",
        }

    def test_total_score_within_range(self):
        result = score_job(self._base_job())
        assert 0 <= result["total_score"] <= 100

    def test_no_sponsor_zeroes_visa_score(self):
        result = score_job(self._base_job(visa_signal=-1))
        assert result["visa_score"] == 0.0

    def test_senior_penalty_applied(self):
        normal = score_job(self._base_job())
        senior = score_job(self._base_job(title="Senior Software Engineer"))
        assert senior["total_score"] == pytest.approx(normal["total_score"] * 0.35, rel=1e-3)

    def test_junior_title_no_penalty(self):
        normal = score_job(self._base_job())
        junior = score_job(self._base_job(title="New Grad Software Engineer"))
        # Neither title triggers senior check — scores should be equal
        assert junior["total_score"] == pytest.approx(normal["total_score"], rel=1e-3)


# ── matched_skills ────────────────────────────────────────────────────────────

class TestMatchedSkills:
    def test_python_in_matched(self):
        matched, _ = matched_skills("We need a python developer.")
        assert "python" in matched

    def test_react_in_matched(self):
        matched, _ = matched_skills("React frontend developer.")
        assert "react" in matched

    def test_empty_gives_no_matched(self):
        matched, _ = matched_skills("")
        assert matched == []

    def test_matched_capped_at_ten(self):
        desc = "python java javascript typescript golang react nodejs django flask nextjs fastapi spring aws gcp azure kubernetes docker pytorch tensorflow scikit-learn"
        matched, _ = matched_skills(desc)
        assert len(matched) <= 10

    def test_missing_capped_at_six(self):
        _, missing = matched_skills("")
        assert len(missing) <= 6
