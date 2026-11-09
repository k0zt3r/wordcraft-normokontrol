"""Default stamp fonts and diagnostics must not depend on ISOCPEUR."""
from pathlib import Path
import os
import unittest
from unittest.mock import patch

import agent_api
from format_profile import DEFAULT_PATH, load


class StampFontTests(unittest.TestCase):
    def test_default_profile_uses_times_at_original_sizes(self):
        values = load(DEFAULT_PATH.parent / 'nonexistent-test-overrides.json')
        self.assertEqual(values['stamp_font'], 'Times New Roman')
        self.assertEqual(values['stamp_size'], 9)
        self.assertEqual(values['stamp_code_size'], 16)

    @unittest.skipUnless(os.name == 'nt', 'Windows installed fonts')
    def test_default_font_check_does_not_require_isocpeur(self):
        import pymupdf
        actual = pymupdf.Font
        def without_isocpeur(*args, **kwargs):
            if 'iso' in Path(kwargs.get('fontfile', '')).name.casefold():
                raise ValueError('ISOCPEUR unavailable')
            return actual(*args, **kwargs)
        with patch.object(pymupdf, 'Font', side_effect=without_isocpeur):
            result = agent_api._font_check()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['family'], 'Times New Roman')
        self.assertTrue(all('Times New Roman' in font['name'] for font in result['fonts']))

    @unittest.skipUnless(os.name == 'nt', 'Windows installed fonts')
    def test_custom_font_is_not_replaced_by_default_during_diagnosis(self):
        with patch.object(Path, 'glob', return_value=[]):
            result = agent_api._font_check('Missing Custom Stamp Font 999')
        self.assertFalse(result['ok'])
        self.assertEqual(result['family'], 'Missing Custom Stamp Font 999')
        self.assertEqual(result['fonts'], [])


if __name__ == '__main__':
    unittest.main()
