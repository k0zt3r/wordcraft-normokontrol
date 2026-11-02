"""Run the standalone GUI or pass CLI options to the normalisation script."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    recovery = runpy.run_path(str(Path(__file__).resolve().parent / '_normokontrol_recovery.py'))
    recovery['recover'](Path(__file__).resolve().parent)
    runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "normokontrol.py"), run_name="__main__")
