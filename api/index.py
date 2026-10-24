# -*- coding: utf-8 -*-
"""Vercel entrypoint: يضيف مجلد backend إلى sys.path ثم يصدّر تطبيق Flask."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, 'backend')
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app import app  # noqa: E402

# Vercel يبحث عن متغير باسم app أو handler
handler = app
