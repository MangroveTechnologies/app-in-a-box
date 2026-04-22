"""Unit tests for src.shared.timeframes.

Covers:
- Canonical whitelist matches upstream SUPPORTED_TIMEFRAMES.
- 1m is explicitly rejected (the agent tried this, got silent 1h fallback).
- Aliases resolve to canonical form.
- recommended_lookback_months matches the upstream prompt_builder doc
  (5m/15m/30m/1h → 3, 4h → 6, 1d → 12).
"""
import pytest

from src.shared import timeframes
from src.shared.errors import ValidationError


class TestCanonicalize:
    @pytest.mark.parametrize("tf", ["5m", "15m", "30m", "1h", "4h", "1d"])
    def test_canonical_accepted(self, tf):
        assert timeframes.canonicalize_timeframe(tf) == tf

    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("1HR", "1h"), ("1hr", "1h"),
            ("4HR", "4h"), ("4hr", "4h"),
            ("1D", "1d"), ("1DAY", "1d"), ("1day", "1d"),
            ("5MIN", "5m"), ("5min", "5m"),
            ("15min", "15m"),
            ("30MIN", "30m"),
        ],
    )
    def test_aliases_canonicalize(self, alias, canonical):
        assert timeframes.canonicalize_timeframe(alias) == canonical

    def test_1m_rejected(self):
        # This is the exact case that bit the agent — 1m silently fell
        # back to 1h on the server. We reject it here with a clear error.
        with pytest.raises(ValidationError) as exc:
            timeframes.canonicalize_timeframe("1m")
        assert "not supported" in str(exc.value)
        assert "1h" in exc.value.suggestion or "supported" in exc.value.suggestion.lower()

    @pytest.mark.parametrize("tf", ["", None, "2h", "1week", "1y", "nonsense"])
    def test_other_unsupported_rejected(self, tf):
        with pytest.raises(ValidationError):
            timeframes.canonicalize_timeframe(tf)


class TestRecommendedLookback:
    @pytest.mark.parametrize(
        "tf,expected_months",
        [
            ("5m", 3), ("15m", 3), ("30m", 3), ("1h", 3),
            ("4h", 6),
            ("1d", 12), ("1D", 12),
        ],
    )
    def test_matches_upstream_doc(self, tf, expected_months):
        """Must match MangroveAI's ai_copilot/agentic/prompt_builder.py."""
        assert timeframes.recommended_lookback_months(tf) == expected_months

    def test_unsupported_tf_raises(self):
        with pytest.raises(ValidationError):
            timeframes.recommended_lookback_months("1m")
