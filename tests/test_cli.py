import unittest
import subprocess
import sys
from pdf_contract_masking import mask_text


class TestCLI(unittest.TestCase):
    def test_cli_outputs_masked(self):
        # Run the CLI module directly
        result = subprocess.run([sys.executable, "-m", "pdf_contract_masking.cli", "123456"], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "**3456")


if __name__ == "__main__":
    unittest.main()
