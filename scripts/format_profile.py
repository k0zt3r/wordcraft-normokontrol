"""Validated formatting values; local overrides survive program updates."""
import json
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / 'assets' / 'format-profile.json'
def user_file(name):
    """System packages are read-only; portable copies retain local settings."""
    if (ROOT / '.normokontrol-deb').exists():
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        return base / 'wordcraft-normokontrol' / name
    return ROOT / name


LOCAL_PATH = user_file('.normokontrol-profile.json')
BOUNDS = {'text_size': (10,24), 'line_spacing': (1,3), 'body_indent_mm': (0,30),
          'compact_indent_mm': (0,30), 'chapter_gap_pt': (0,72), 'subheading_gap_pt': (0,72),
          'stamp_size': (4,24), 'stamp_code_size': (4,24), 'frame_stroke_pt': (.1,3),
          'cover_department_gap_pt':(0,72), 'cover_bottom_mm':(10,40)}


def validate(values):
    for key, (low, high) in BOUNDS.items():
        value = values.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not low <= value <= high:
            raise ValueError(f'Параметр {key}: допустимо число от {low} до {high}.')
    for key in ('font','stamp_font'):
        if not isinstance(values.get(key),str) or not values[key].strip():
            raise ValueError(f'Не указан шрифт {key}.')
    return values


def load(local=LOCAL_PATH):
    registry=ROOT/'references/norm-source/requirements.json'
    if registry.exists():
        expected=json.loads(registry.read_text(encoding='utf-8'))['source_sha256']
        if hashlib.sha256((ROOT/'Normokontrol.pdf').read_bytes()).hexdigest()!=expected:
            raise ValueError('PDF нормоконтроля изменён. Повторите извлечение и сверку реестра требований.')
    defaults = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    if Path(local).exists():
        overrides = json.loads(Path(local).read_text(encoding='utf-8'))
        unknown = set(overrides) - set(BOUNDS) - {'font','stamp_font'}
        if unknown:
            raise ValueError('Неизвестные параметры профиля: ' + ', '.join(sorted(unknown)))
        # Formatting explicitly fixed by the PDF cannot be overridden by old preferences.
        locked={'font','text_size','line_spacing','body_indent_mm','frame_stroke_pt','chapter_gap_pt','subheading_gap_pt'}
        defaults.update({k:v for k,v in overrides.items() if k not in locked})
    return validate(defaults)


PROFILE = load()
