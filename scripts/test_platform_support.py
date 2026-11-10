import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import format_profile
from runtime import open_path
import agent_api


class PlatformTests(unittest.TestCase):
    def test_deb_settings_use_user_config_and_portable_settings_stay_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(format_profile, 'ROOT', root), patch.dict(os.environ, {'XDG_CONFIG_HOME': str(root / 'config')}):
                self.assertEqual(format_profile.user_file('settings'), root / 'settings')
                (root / '.normokontrol-deb').touch()
                self.assertEqual(format_profile.user_file('settings'), root / 'config/wordcraft-normokontrol/settings')

    def test_linux_opener_passes_path_as_one_argument(self):
        with patch('os.name', 'posix'), \
                patch('sys.platform', 'linux'), patch('subprocess.Popen') as launch:
            open_path('/tmp/работа ; name/report.html')
        launch.assert_called_once_with(['xdg-open', '/tmp/работа ; name/report.html'])

    def test_fontconfig_substitution_is_not_success(self):
        from types import SimpleNamespace
        with patch.object(agent_api.os, 'name', 'posix'), patch('subprocess.run', return_value=SimpleNamespace(stdout='Liberation Serif\nRegular\n/font.ttf\n')):
            self.assertFalse(agent_api._font_check()['ok'])


if __name__ == '__main__':
    unittest.main()
