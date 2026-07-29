"""Protein-network features (Context.md §14.5, §18.1).

Built from the STRING v12 gene-level network (``data/string_db.py``), which
yields ~930k undirected edges at the medium-confidence threshold.

Two cautions:

* **Degree is confounded with study effort.** Well-studied proteins have more
  recorded interactions, so raw degree partly measures attention rather than
  biology — the network analogue of the publication bias in Context.md §32.2.
* **The confidence threshold is a modelling decision**, not an implementation
  detail. It changes the graph and therefore every feature here, so record it
  alongside the results (Context.md §33).

Context.md §18.3 is explicit that a GNN should not be added merely because it is
more advanced; these hand-computed features are the baseline it would have to
beat.
"""

from __future__ import annotations

import networkx as nx
import polars as pl

__all__ = ["build_network_features", "distance_to_disease_genes", "load_graph"]


def load_graph(min_score: int = 400) -> nx.Graph:
    """Build a NetworkX graph from the STRING gene-level edge list."""
    raise NotImplementedError("Milestone 1")


def distance_to_disease_genes(
    graph: nx.Graph,
    gene_ids: list[str],
    disease_genes: list[str],
) -> pl.DataFrame:
    """Shortest-path distance from each gene to the nearest known disease gene.

    Genes in a disconnected component have no path. Record that as null with a
    missing indicator, not as infinity or a large sentinel — a sentinel becomes
    a real number to a tree model and invents an ordering.
    """
    raise NotImplementedError("Milestone 1")


def build_network_features(
    gene_ids: list[str],
    disease_genes: list[str] | None = None,
    min_score: int = 400,
) -> pl.DataFrame:
    """Derive network features. See ``groups.network`` in features.yaml."""
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.network")
