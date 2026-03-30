"""Tests for the QoL Diagnostics module."""

import sys

from qol_pack.events import ErrorCapturedEvent, ConflictDetectedEvent, SettingsChangedEvent
from qol_pack._compat import EventBus, ModRegistry, Diagnostics
from qol_pack.modules.diagnostics import (
    QoLDiagnostics,
    _identify_mod_from_traceback,
    _suggest_fix,
    _simplify_traceback,
    KNOWN_CONFLICTS,
    ERROR_PATTERNS,
)


class TestQoLDiagnosticsInstall:
    def test_install_replaces_excepthook(self):
        original = sys.excepthook
        QoLDiagnostics.install()
        assert sys.excepthook is not original
        assert sys.excepthook == QoLDiagnostics._exception_handler
        QoLDiagnostics.uninstall()

    def test_uninstall_restores_excepthook(self):
        original = sys.excepthook
        QoLDiagnostics.install()
        QoLDiagnostics.uninstall()
        assert sys.excepthook is original

    def test_install_idempotent(self):
        QoLDiagnostics._installed = False
        QoLDiagnostics.install()
        QoLDiagnostics.install()  # Should not raise
        QoLDiagnostics.uninstall()

    def test_subscribes_to_settings(self):
        QoLDiagnostics._installed = False
        QoLDiagnostics.install()
        subs = EventBus.get_subscribers(SettingsChangedEvent)
        mod_ids = [s.mod_id for s in subs]
        assert "stark_qol_pack.diagnostics" in mod_ids
        QoLDiagnostics.uninstall()


class TestExceptionHandler:
    def setup_method(self):
        QoLDiagnostics._installed = False
        QoLDiagnostics._error_count = 0

    def test_exception_handler_records_error(self):
        QoLDiagnostics.install()

        try:
            raise ValueError("test error for diagnostics")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            QoLDiagnostics._exception_handler(exc_type, exc_value, exc_tb)

        assert QoLDiagnostics._error_count == 1
        errors = Diagnostics.get_errors()
        assert len(errors) >= 1
        assert errors[0]["error"] == "test error for diagnostics"
        QoLDiagnostics.uninstall()

    def test_exception_handler_publishes_event(self):
        QoLDiagnostics.install()
        events = []

        @EventBus.on(ErrorCapturedEvent)
        def capture(event):
            events.append(event)

        try:
            raise TypeError("test type error")
        except TypeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            QoLDiagnostics._exception_handler(exc_type, exc_value, exc_tb)

        assert len(events) == 1
        assert events[0].error_type == "TypeError"
        assert events[0].message == "test type error"
        QoLDiagnostics.uninstall()


class TestConflictDetection:
    def test_known_conflict_detected(self):
        ModRegistry.register(
            mod_id="stark_qol_pack", name="QoL", version="0.1.0",
        )
        ModRegistry.register(
            mod_id="weerbesu_ui_cheats", name="UI Cheats", version="1.0.0",
        )

        events = []

        @EventBus.on(ConflictDetectedEvent)
        def capture(event):
            events.append(event)

        QoLDiagnostics._installed = False
        QoLDiagnostics.install()
        conflicts = QoLDiagnostics.detect_conflicts()

        assert len(conflicts) >= 1
        known = [c for c in conflicts if c.get("type") == "known_conflict"]
        assert len(known) >= 1
        assert len(events) >= 1
        QoLDiagnostics.uninstall()

    def test_no_conflict_when_clean(self):
        ModRegistry.register(
            mod_id="stark_qol_pack", name="QoL", version="0.1.0",
        )
        QoLDiagnostics._installed = False
        QoLDiagnostics.install()
        conflicts = QoLDiagnostics.detect_conflicts()
        known = [c for c in conflicts if c.get("type") == "known_conflict"]
        assert len(known) == 0
        QoLDiagnostics.uninstall()


class TestModIdentification:
    def test_identify_qol_pack(self):
        tb_lines = [
            'Traceback (most recent call last):',
            '  File "/path/to/qol_pack/modules/ui_tweaks.py", line 42',
            '    some_code()',
            'ValueError: bad value',
        ]
        assert _identify_mod_from_traceback(tb_lines) == "stark_qol_pack"

    def test_identify_framework(self):
        tb_lines = [
            'Traceback (most recent call last):',
            '  File "/path/to/stark_framework/core/events.py", line 10',
            '    handler(event)',
            'RuntimeError: handler failed',
        ]
        assert _identify_mod_from_traceback(tb_lines) == "stark_framework"

    def test_identify_unknown(self):
        tb_lines = [
            'Traceback (most recent call last):',
            '  File "/some/random/path.py", line 5',
            'RuntimeError: mystery error',
        ]
        assert _identify_mod_from_traceback(tb_lines) == "unknown"


class TestSuggestFix:
    def test_attribute_error_sim_info(self):
        fix = _suggest_fix(
            "AttributeError: 'NoneType' object has no attribute 'sim_info'",
            "traceback with sim_info references",
            "test_mod",
        )
        assert "Sim reference became None" in fix

    def test_import_error(self):
        fix = _suggest_fix(
            "ImportError: No module named 'missing_mod'",
            "",
            "test_mod",
        )
        assert "required module is missing" in fix

    def test_recursion_error(self):
        fix = _suggest_fix(
            "RecursionError: maximum recursion depth exceeded",
            "",
            "test_mod",
        )
        assert "Infinite loop" in fix

    def test_unknown_error_generic_fix(self):
        fix = _suggest_fix(
            "SomeWeirdError: never seen before",
            "no matching patterns here",
            "my_mod",
        )
        assert "my_mod" in fix
        assert "update" in fix.lower()


class TestSimplifyTraceback:
    def test_simplifies_long_traceback(self):
        full_tb = "\n".join([
            "Traceback (most recent call last):",
            '  File "/path/a.py", line 1, in func_a',
            "    func_b()",
            '  File "/path/b.py", line 2, in func_b',
            "    func_c()",
            '  File "/path/c.py", line 3, in func_c',
            "    raise ValueError('oops')",
            "ValueError: oops",
        ])
        simplified = _simplify_traceback(full_tb)
        assert "ValueError: oops" in simplified
        # Should keep File references
        assert "File" in simplified


class TestBugReport:
    def test_generate_bug_report(self, tmp_path):
        import json
        ModRegistry.register(
            mod_id="stark_qol_pack", name="QoL", version="0.1.0",
        )
        QoLDiagnostics._installed = False
        QoLDiagnostics.install()

        report_path = str(tmp_path / "report.json")
        result = QoLDiagnostics.generate_bug_report(output_path=report_path)
        assert result == report_path

        with open(report_path) as f:
            report = json.load(f)

        assert "qol_version" in report
        assert "loaded_mods" in report
        assert "detected_conflicts" in report
        QoLDiagnostics.uninstall()


class TestErrorSummary:
    def test_error_summary_groups_by_mod(self):
        Diagnostics.record_error("mod_a", ValueError("err1"), "ctx1")
        Diagnostics.record_error("mod_a", ValueError("err2"), "ctx2")
        Diagnostics.record_error("mod_b", TypeError("err3"), "ctx3")

        summary = QoLDiagnostics.get_error_summary()
        assert summary["mod_a"]["count"] == 2
        assert summary["mod_b"]["count"] == 1
