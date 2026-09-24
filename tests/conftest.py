import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "desktop-pet" / "assets" / "python"))
sys.path.insert(0, str(ROOT / "skills" / "desktop-pet" / "scripts"))
