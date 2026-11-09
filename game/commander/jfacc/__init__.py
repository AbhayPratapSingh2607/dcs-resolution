"""Doctrine-driven air campaign planner (a JFACC model).

The planner plans each turn as one air tasking order period (6 hours by
default), top down: campaign assessment, phase, target list (JIPTL),
apportionment, threat-scaled packages and a deconflicted timeline. See
planner.py for the entry point. This package must stay import-light: its
modules are imported lazily from the game and coalition code.
"""
