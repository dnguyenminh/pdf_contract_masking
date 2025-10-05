import unittest
from pdf_contract_masking import mask_text


class TestMaskText(unittest.TestCase):
    def test_masking_default(self):
        self.assertEqual(mask_text("1234567890"), "******7890")

    def test_mask_shorter_than_keep(self):
        self.assertEqual(mask_text("123"), "123")

    def test_keep_zero(self):
        self.assertEqual(mask_text("abcd", keep_last=0), "****")

    def test_negative_keep_raises(self):
        with self.assertRaises(ValueError):
            mask_text("abcd", keep_last=-1)


if __name__ == "__main__":
    unittest.main()
