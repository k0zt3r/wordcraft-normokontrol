"""Validated formatting values; local overrides survive program updates."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / 'assets' / 'format-profile.json'
LOCAL_PATH = ROOT / '.normokontrol-profile.json'
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
    defaults = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    if Path(local).exists():
        overrides = json.loads(Path(local).read_text(encoding='utf-8'))
        unknown = set(overrides) - set(BOUNDS) - {'font','stamp_font'}
        if unknown:
            raise ValueError('Неизвестные параметры профиля: ' + ', '.join(sorted(unknown)))
        defaults.update(overrides)
    return validate(defaults)


PROFILE = load()
