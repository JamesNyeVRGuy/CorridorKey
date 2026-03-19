"""Tests for GPU credit tracking (CRKY-6)."""

import pytest

from web.api.gpu_credits import OrgCredits, add_consumed, add_contributed, get_org_credits


@pytest.fixture
def credits_store(tmp_path):
    """Initialize storage for credit tests."""
    from web.api import database as db_mod
    from web.api import persist

    persist.init(str(tmp_path))
    db_mod._backend = None
    yield
    db_mod._backend = None


class TestOrgCredits:
    def test_balance_surplus(self):
        c = OrgCredits(org_id="o1", contributed_seconds=100, consumed_seconds=60)
        assert c.balance == 40

    def test_balance_deficit(self):
        c = OrgCredits(org_id="o1", contributed_seconds=50, consumed_seconds=80)
        assert c.balance == -30

    def test_ratio_normal(self):
        c = OrgCredits(org_id="o1", contributed_seconds=100, consumed_seconds=50)
        assert c.ratio == 0.5

    def test_ratio_zero_contributed(self):
        c = OrgCredits(org_id="o1", contributed_seconds=0, consumed_seconds=50)
        assert c.ratio == float("inf")

    def test_ratio_zero_both(self):
        c = OrgCredits(org_id="o1", contributed_seconds=0, consumed_seconds=0)
        assert c.ratio == 0.0

    def test_to_dict(self):
        c = OrgCredits(org_id="o1", contributed_seconds=3600, consumed_seconds=1800)
        d = c.to_dict()
        assert d["contributed_hours"] == 1.0
        assert d["consumed_hours"] == 0.5
        assert d["balance_seconds"] == 1800.0


class TestCreditTracking:
    def test_add_contributed(self, credits_store):
        add_contributed("org-1", 100)
        credits = get_org_credits("org-1")
        assert credits.contributed_seconds == 100

    def test_add_consumed(self, credits_store):
        add_consumed("org-1", 50)
        credits = get_org_credits("org-1")
        assert credits.consumed_seconds == 50

    def test_accumulates(self, credits_store):
        add_contributed("org-1", 100)
        add_contributed("org-1", 200)
        credits = get_org_credits("org-1")
        assert credits.contributed_seconds == 300

    def test_separate_orgs(self, credits_store):
        add_contributed("org-1", 100)
        add_contributed("org-2", 200)
        assert get_org_credits("org-1").contributed_seconds == 100
        assert get_org_credits("org-2").contributed_seconds == 200

    def test_empty_org(self, credits_store):
        credits = get_org_credits("nonexistent")
        assert credits.contributed_seconds == 0
        assert credits.consumed_seconds == 0

    def test_ignores_zero(self, credits_store):
        add_contributed("org-1", 0)
        add_consumed("org-1", 0)
        credits = get_org_credits("org-1")
        assert credits.contributed_seconds == 0

    def test_ignores_negative(self, credits_store):
        add_contributed("org-1", -50)
        credits = get_org_credits("org-1")
        assert credits.contributed_seconds == 0

    def test_ignores_empty_org_id(self, credits_store):
        add_contributed("", 100)
        add_consumed("", 100)
        # Should not create an entry for empty org_id
