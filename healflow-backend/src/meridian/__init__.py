"""Meridian platform kernel.

Layers (architecture §1, frozen):
  L1 store      — append-only clinical event store, hash-chained
  L2 projector  — pure fold framework with checkpoints and replay
  L3 read models— disposable rm_* tables owned by projectors
  L4-L8 engines — recovery, risk, trust, recommendation, ranking
  L9 brief      — renders ranked Decisions; owns zero clinical logic

Kernel laws (constitution E1-E3, enforced by tests):
  - No wall clock inside engines: every computation takes explicit `as_of`.
  - Every derived value carries the event ids it rests on (Evidence).
  - Reset + replay must reproduce the ranked decision list bit-identically.
"""
