import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, ROOT)
os.environ.setdefault('HARNESS_DATA_DIR', str(Path(ROOT) / '.data'))

import uvicorn

uvicorn.run('app.main:create_app', factory=True, host='127.0.0.1',
            port=int(os.getenv('HARNESS_PORT', '8000')), access_log=False,
            proxy_headers=False)
