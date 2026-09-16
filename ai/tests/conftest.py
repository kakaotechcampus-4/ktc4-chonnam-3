"""Make sibling test-support modules (e.g. eval_loader.py) importable.

--import-mode=importlib does not add this directory to sys.path on its own.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
