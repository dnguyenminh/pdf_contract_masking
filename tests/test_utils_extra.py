import unittest
from pdf_contract_masking import mask_text


class TestMaskTextExtra(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(mask_text(None), "")


if __name__ == "__main__":
    unittest.main()
