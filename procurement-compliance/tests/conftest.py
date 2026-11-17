import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("PCS_KG_BACKEND", "mini")
os.environ.setdefault("PCS_REASONER", "rule")
os.environ.pop("PCS_MCP_URL", None)
