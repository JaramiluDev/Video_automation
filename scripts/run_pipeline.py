#!/usr/bin/env python3
"""
Pipeline E2E por episodio: guion YAML → audio multi-voz → video base
sincronizado con ese audio (heavy_render, HG) → video final → YouTube.

    python scripts/run_pipeline.py -s GUION-02 --fast            # borrador 480p
    python scripts/run_pipeline.py -s GUION-02 --production --reuse-audio

La lógica vive en src/video_automation/pipeline.py (una sola copia).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from video_automation.pipeline import main  # noqa: E402

if __name__ == "__main__":
    main()
