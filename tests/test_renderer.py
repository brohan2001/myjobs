from __future__ import annotations

from src.renderer import _role_badge_class, _visa_class, _visa_label


class TestVisaLabel:
    def test_confirmed(self):
        assert _visa_label(1) == "CONFIRMED"

    def test_no_sponsor(self):
        assert _visa_label(-1) == "NO SPONSOR"

    def test_unknown(self):
        assert _visa_label(0) == "UNCONFIRMED"


class TestVisaClass:
    def test_yes(self):
        assert _visa_class(1) == "visa-yes"

    def test_no(self):
        assert _visa_class(-1) == "visa-no"

    def test_unknown(self):
        assert _visa_class(0) == "visa-unknown"


class TestRoleBadgeClass:
    def test_all_known_roles(self):
        known = {
            "backend":   "role-backend",
            "cloud":     "role-cloud",
            "fullstack": "role-fullstack",
            "frontend":  "role-frontend",
            "mobile":    "role-mobile",
            "network":   "role-network",
            "ds":        "role-ds",
            "ml":        "role-ml",
        }
        for role, expected in known.items():
            assert _role_badge_class(role) == expected

    def test_unknown_role_returns_other(self):
        assert _role_badge_class("unicorn") == "role-other"

    def test_empty_string_returns_other(self):
        assert _role_badge_class("") == "role-other"
