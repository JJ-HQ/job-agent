"""Registre des sources. Une source = un module avec NAME, ENV et search(...).

Pour en ajouter une : créer le module, l'ajouter ci-dessous et dans config.example.yml.
"""
from . import adzuna, jooble

SOURCES = {m.NAME: m for m in (adzuna, jooble)}
