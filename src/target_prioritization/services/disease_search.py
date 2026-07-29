"""Disease search for the UI (Context.md §21 MVP interface).

This is the one place the Open Targets **GraphQL API** is appropriate: resolving
a free-text disease name typed by a user, with autocomplete. Everything the
pipeline reads comes from the pinned FTP release instead, so results stay
reproducible (Context.md §32.7).

For the ten MVP diseases, prefer the already-resolved IDs in
``configs/diseases.yaml`` over a live lookup — they were resolved against the
same release the features were built from, and a live API result can point at a
disease ID the local data does not contain.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DiseaseSearchResult", "search_diseases", "suggest"]


@dataclass(slots=True)
class DiseaseSearchResult:
    disease_id: str
    name: str
    description: str | None
    therapeutic_areas: list[str]
    n_associated_targets: int | None = None


def search_diseases(query: str, limit: int = 10) -> list[DiseaseSearchResult]:
    """Search diseases by name or synonym.

    Searches the local ``disease`` table first so the result is guaranteed to
    exist in the pinned release, falling back to the GraphQL API only for names
    it cannot resolve.
    """
    raise NotImplementedError("Milestone 3 — Context.md §21")


def suggest(prefix: str, limit: int = 10) -> list[str]:
    """Autocomplete suggestions for a partial disease name."""
    raise NotImplementedError("Milestone 3")
