import unittest
from morph.util import extract_json

class Json(unittest.TestCase):
    def test_fenced(self):
        self.assertEqual(extract_json('x ```json\n{"severity":0.2}\n``` y')["severity"], 0.2)

if __name__ == "__main__":
    unittest.main()
