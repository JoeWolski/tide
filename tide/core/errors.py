"""Typed errors and deterministic exit codes."""

from __future__ import annotations

from dataclasses import dataclass


class TideError(Exception):
    """Base error for deterministic CLI exits."""

    exit_code: int = 3


class InputError(TideError):
    exit_code = 2


class GitError(TideError):
    exit_code = 3


@dataclass(slots=True)
class ConflictError(TideError):
    operation: str
    branches: list[str]
    files: list[str]

    exit_code: int = 4


class ForgeError(TideError):
    exit_code = 5


class AmbiguityError(TideError):
    exit_code = 6
