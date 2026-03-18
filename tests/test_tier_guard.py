"""Tests for trust tier route guards."""

import pytest

from web.api.auth import UserContext


class TestTierHierarchy:
    """Verify the tier hierarchy property checks."""

    TIERS = ["pending", "member", "contributor", "org_admin", "platform_admin"]

    def test_member_and_above(self):
        for tier in self.TIERS:
            user = UserContext(user_id="test", tier=tier)
            if tier in ("member", "contributor", "org_admin", "platform_admin"):
                assert user.is_member, f"{tier} should be a member"
            else:
                assert not user.is_member, f"{tier} should not be a member"

    def test_contributor_and_above(self):
        for tier in self.TIERS:
            user = UserContext(user_id="test", tier=tier)
            if tier in ("contributor", "org_admin", "platform_admin"):
                assert user.is_contributor, f"{tier} should be a contributor"
            else:
                assert not user.is_contributor, f"{tier} should not be a contributor"

    def test_admin_only(self):
        for tier in self.TIERS:
            user = UserContext(user_id="test", tier=tier)
            if tier == "platform_admin":
                assert user.is_admin, f"{tier} should be admin"
            else:
                assert not user.is_admin, f"{tier} should not be admin"

    def test_require_tier_rejects_lower(self):
        """require_tier should raise 403 for insufficient tier."""
        from unittest.mock import MagicMock

        from web.api.auth import require_tier

        request = MagicMock()
        request.state.user = UserContext(user_id="test", tier="member")

        # Member can't access contributor-level routes
        with pytest.raises(Exception) as exc_info:
            require_tier(request, "contributor")
        assert "403" in str(exc_info.value.status_code)

    def test_require_tier_allows_equal(self):
        from unittest.mock import MagicMock

        from web.api.auth import require_tier

        request = MagicMock()
        request.state.user = UserContext(user_id="test", tier="contributor")
        result = require_tier(request, "contributor")
        assert result.tier == "contributor"

    def test_require_tier_allows_higher(self):
        from unittest.mock import MagicMock

        from web.api.auth import require_tier

        request = MagicMock()
        request.state.user = UserContext(user_id="test", tier="platform_admin")
        result = require_tier(request, "member")
        assert result.tier == "platform_admin"
