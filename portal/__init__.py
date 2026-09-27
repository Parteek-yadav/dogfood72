"""
Dogfood Portal package initialization.
"""

import sys

# Python 3.14 compatibility fix for Django 5.1 BaseContext.__copy__
# In Python 3.14+, copy(super()) copies the super proxy rather than self.
if sys.version_info >= (3, 14):
    try:
        from django.template import context

        def _base_context_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            duplicate.__dict__.update(self.__dict__)
            duplicate.dicts = self.dicts[:]
            return duplicate

        context.BaseContext.__copy__ = _base_context_copy
    except ImportError:
        pass
