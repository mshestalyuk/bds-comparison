"""
Abstract base class for all database runners.
Each runner must implement all 12 benchmark scenarios.
"""
import time
from abc import ABC, abstractmethod
from typing import List


class BaseRunner(ABC):
    """
    Lifecycle per dataset size:
        setup(n)                     ← load n records, build internal state
        for scenario in SCENARIOS:
            for attempt in range(ATTEMPTS):
                before_scenario(sid) ← insert pool data if needed (NOT timed)
                t = run_scenario(sid)← measured operation(s), returns ms
                after_scenario(sid)  ← cleanup pool data if needed (NOT timed)
        teardown()                   ← wipe all benchmark data
    """

    def __init__(self):
        self._n: int = 0                  # current dataset size
        self._pool_ids: List[int] = []    # IDs prepared for current scenario
        self._sample_ids: List[int] = []  # random IDs from main dataset

    # ------------------------------------------------------------------
    # Subclass must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def setup(self, n: int) -> None:
        """Load n records into the database and cache internal state."""

    @abstractmethod
    def teardown(self) -> None:
        """Drop all benchmark data and close connections."""

    @abstractmethod
    def before_scenario(self, scenario_id: str) -> None:
        """Prepare pool data required by this scenario (not timed)."""

    @abstractmethod
    def run_scenario(self, scenario_id: str) -> float:
        """Execute the scenario, return elapsed time in milliseconds."""

    @abstractmethod
    def after_scenario(self, scenario_id: str) -> None:
        """Clean up any leftover pool data (not timed)."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def max_dataset_size(self) -> int:
        return 1_000_000

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable runner name."""

    @staticmethod
    def _now_ms() -> float:
        return time.perf_counter() * 1_000
