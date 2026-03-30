"""Tests for XML tuning override files.

Validates that all tuning files exist, are well-formed XML, and contain
the expected tuning parameters with documented values.
"""

import os
import xml.etree.ElementTree as ET

import pytest

TUNING_DIR = os.path.join(os.path.dirname(__file__), "..", "tuning")


def _tuning_path(name):
    return os.path.join(TUNING_DIR, name)


class TestTuningFilesExist:
    def test_autonomy_timing_exists(self):
        assert os.path.isfile(_tuning_path("autonomy_timing.xml"))

    def test_time_scale_exists(self):
        assert os.path.isfile(_tuning_path("time_scale.xml"))

    def test_routing_optimization_exists(self):
        assert os.path.isfile(_tuning_path("routing_optimization.xml"))


class TestTuningWellFormed:
    """Every tuning XML must parse without errors."""

    @pytest.mark.parametrize("filename", [
        "autonomy_timing.xml",
        "time_scale.xml",
        "routing_optimization.xml",
    ])
    def test_xml_parses(self, filename):
        tree = ET.parse(_tuning_path(filename))
        root = tree.getroot()
        assert root.tag == "I"
        assert root.attrib.get("n") is not None


class TestAutonomyTiming:
    def setup_method(self):
        tree = ET.parse(_tuning_path("autonomy_timing.xml"))
        self.root = tree.getroot()
        self.params = {t.attrib["n"]: t.text for t in self.root.findall("T")}

    def test_has_reevaluation_interval(self):
        assert "autonomy_reevaluation_interval_min" in self.params

    def test_reevaluation_interval_increased(self):
        val = int(self.params["autonomy_reevaluation_interval_min"])
        assert val > 5, "Should be higher than vanilla default of 5"
        assert val <= 20, "Should not exceed 20 Sim-minutes"

    def test_has_multitasking_break_interval(self):
        assert "multitasking_break_interval_min" in self.params

    def test_multitasking_break_increased(self):
        val = int(self.params["multitasking_break_interval_min"])
        assert val > 15, "Should be higher than vanilla default of 15"
        assert val <= 60, "Should not exceed 60 Sim-minutes"

    def test_has_max_requests_per_tick(self):
        assert "max_autonomy_requests_per_tick" in self.params

    def test_max_requests_reduced(self):
        val = int(self.params["max_autonomy_requests_per_tick"])
        assert val < 8, "Should be lower than vanilla default of 8"
        assert val >= 2, "Should not go below 2"


class TestTimeScale:
    def setup_method(self):
        tree = ET.parse(_tuning_path("time_scale.xml"))
        self.root = tree.getroot()
        self.params = {t.attrib["n"]: t.text for t in self.root.findall("T")}

    def test_speed_1_unchanged(self):
        val = int(self.params["speed_1_time_scale"])
        assert val == 25, "Speed 1 should remain at vanilla default"

    def test_speed_2_reduced(self):
        val = int(self.params["speed_2_time_scale"])
        assert val < 100, "Speed 2 should be reduced from vanilla 100"
        assert val >= 50, "Speed 2 should not go below 50"

    def test_speed_3_reduced(self):
        val = int(self.params["speed_3_time_scale"])
        assert val < 1000, "Speed 3 should be reduced from vanilla 1000"
        assert val >= 250, "Speed 3 should not go below 250"

    def test_low_perf_threshold_reduced(self):
        val = int(self.params["low_performance_threshold_ms"])
        assert val < 10000, "Should trigger recovery earlier than vanilla 10000ms"
        assert val >= 2000, "Should not be too aggressive"


class TestRoutingOptimization:
    def setup_method(self):
        tree = ET.parse(_tuning_path("routing_optimization.xml"))
        self.root = tree.getroot()
        self.params = {t.attrib["n"]: t.text for t in self.root.findall("T")}

    def test_has_idle_recalc_interval(self):
        assert "idle_route_recalc_interval" in self.params

    def test_idle_recalc_increased(self):
        val = int(self.params["idle_route_recalc_interval"])
        assert val > 1, "Should be higher than vanilla 1 (every tick)"
        assert val <= 10, "Should not delay too long"

    def test_has_max_pathfinding_per_tick(self):
        assert "max_pathfinding_per_tick" in self.params

    def test_has_route_cache_duration(self):
        assert "route_cache_duration" in self.params

    def test_route_cache_increased(self):
        val = int(self.params["route_cache_duration"])
        assert val > 10, "Should be higher than vanilla 10"
        assert val <= 50, "Should not cache routes too long"
