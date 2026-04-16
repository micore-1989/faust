"""
Pursuit subsystem — multi-step demo workflows.

A Pursuit is a scripted sequence of skill invocations plus lightweight
bookkeeping (progress updates, activity log, completion poster). See
faust-ui-spec.md §10.4 and §16.5.

Stage 5a (this package) provides:
    - models    : dataclasses for Pursuit, PursuitRun, PursuitResult
    - events    : PursuitStarted / Progress / Activity / Stopped / Complete
    - registry  : 7 predefined + Custom entries with parameter schemas
    - runner    : async orchestrator that shepherds implementations
    - storage   : JSON-lines persistence of PursuitResult

Stage 5b fills in the seven real implementation functions by registering
them in `registry.IMPLEMENTATIONS`.
"""

__all__ = []
