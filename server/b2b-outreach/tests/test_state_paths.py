from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from b2b.paths import data_file, log_dir


class TestStatePaths(unittest.TestCase):
    def test_queue_dir_derives_logs_and_data(self):
        with patch.dict(
            "os.environ",
            {"B2B_QUEUE_DIR": "/var/lib/cazador-de-suenos/b2b-outreach"},
            clear=False,
        ):
            self.assertEqual(
                log_dir(), Path("/var/lib/cazador-de-suenos/b2b-outreach/logs")
            )
            self.assertEqual(
                data_file("registro_leads.json"),
                Path("/var/lib/cazador-de-suenos/b2b-outreach/data/registro_leads.json"),
            )


if __name__ == "__main__":
    unittest.main()
