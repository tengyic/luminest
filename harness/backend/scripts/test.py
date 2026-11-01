import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1')
raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', str(root / 'tests'), '-q', '-p', 'no:cacheprovider'], cwd=root, env=env))
