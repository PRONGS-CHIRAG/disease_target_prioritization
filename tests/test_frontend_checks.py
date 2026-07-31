"""Tests for the Milestone 5 acceptance check (milestone5_plan.md §6).

Runs `run_all_checks()` against the real processed artifacts, real fold
models and real configured diseases — like `scripts/check_frontend.py`
itself, this needs the built artifacts, not synthetic data (the same
standard `app_checks.py`'s equivalent gate holds itself to), hence
`needs_data` rather than the fast synthetic-data style the rest of this
suite prefers.
"""

from __future__ import annotations

import pytest

from target_prioritization.frontend_checks import run_all_checks


@pytest.mark.needs_data
class TestRunAllChecks:
    def test_every_check_passes_against_real_artifacts(self) -> None:
        results = run_all_checks()
        failed = [r for r in results if not r.passed]
        assert not failed, {r.name: r.problems for r in failed}

    def test_six_checks_run(self) -> None:
        results = run_all_checks()
        assert len(results) == 6

    def test_raises_value_error_with_no_diseases(self) -> None:
        with pytest.raises(ValueError, match="No resolved diseases"):
            run_all_checks(diseases=[])
