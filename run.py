# -*- coding: utf-8 -*-
"""便捷入口：`python run.py build -i samples -o output/demo.html`"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
