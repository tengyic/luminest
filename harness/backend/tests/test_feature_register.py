"""The feature register is a contract, so a missing element must fail the suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_every_feature_has_all_six_verification_elements():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / 'scripts' / 'verify_feature_register.py'), '--check'],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert 'register: OK' in result.stdout
