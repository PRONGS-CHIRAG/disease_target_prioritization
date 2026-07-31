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

Exact betweenness centrality is infeasible on this graph (~19.7k nodes, ~930k
edges — O(V·E) is hours to days), so :func:`build_network_features` uses
NetworkX's sampled estimate (:data:`BETWEENNESS_SAMPLE_SIZE` source nodes,
seeded from ``configs/model.yaml``'s ``random_seed`` — milestone4_plan.md
§2.2). The graph and every topology feature computed from it are
disease-agnostic, so both are cached per ``min_score``
(milestone4_plan.md §4.2) rather than recomputed once per disease.

Milestone 4 (see milestone4_plan.md §2.1) does not wire
``net__n_disease_gene_neighbours`` or ``net__min_distance_to_disease_gene``
into the feature table — like pathways.py's deferred columns, both need a
per-disease "known disease genes" seed set this repo has no leakage-reviewed
definition for. :func:`distance_to_disease_genes` is implemented and tested
below so that gap is isolated to "what gene list to pass".
"""

from __future__ import annotations

from functools import cache

import networkx as nx
import polars as pl

from target_prioritization.config import FeaturesConfig, load_model_config
from target_prioritization.data.string_db import MEDIUM_CONFIDENCE, load_gene_level_edges
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "BETWEENNESS_COLUMN",
    "BETWEENNESS_SAMPLE_SIZE",
    "DEGREE_COLUMN",
    "DIMENSION_COLUMN",
    "MEAN_CONFIDENCE_COLUMN",
    "MIN_DISTANCE_COLUMN",
    "MISSING_COLUMN",
    "PAGERANK_COLUMN",
    "WEIGHTED_DEGREE_COLUMN",
    "build_network_features",
    "distance_to_disease_genes",
    "load_graph",
]

log = get_logger(__name__)

DEGREE_COLUMN = "net__degree"
WEIGHTED_DEGREE_COLUMN = "net__weighted_degree"
PAGERANK_COLUMN = "net__pagerank"
BETWEENNESS_COLUMN = "net__betweenness"
MEAN_CONFIDENCE_COLUMN = "net__mean_edge_confidence"
MISSING_COLUMN = "missing__network"
MIN_DISTANCE_COLUMN = "net__min_distance_to_disease_gene"

# dim__network (configs/model.yaml's baseline_weights "network_score",
# Context.md §17.1) — a percentile rank of net__pagerank among the
# candidates *this call was asked to score* (i.e. one disease's candidate
# set), not a fixed threshold: pagerank has no natural [0, 1] scale, unlike
# a saturating count. Illustrative, like every baseline_weights term.
DIMENSION_COLUMN = "dim__network"

# Sampled source-node count for betweenness centrality (module docstring).
BETWEENNESS_SAMPLE_SIZE = 500


@cache
def load_graph(min_score: int = MEDIUM_CONFIDENCE) -> nx.Graph:
    """Build a NetworkX graph from the STRING gene-level edge list.

    Cached per *min_score*: the graph is disease-agnostic, but
    :func:`build_network_features` is called once per disease by
    ``features.build_features.build_feature_table`` — this keeps a
    ten-disease run from reloading and re-collapsing STRING's ~13.7M raw
    edges ten times. The returned graph is shared across callers; treat it
    as read-only.

    Args:
        min_score: Minimum STRING combined score (0-1000 scale) to keep as
            an edge. Defaults to STRING's medium-confidence band.
    """
    edges, report = load_gene_level_edges(min_score=min_score)
    report.log()
    # Sorted explicitly: load_gene_level_edges ends in a polars group_by,
    # which gives no row-order guarantee. Node INSERTION order into the
    # graph then determines which nodes betweenness_centrality's k=500
    # sample draws (NetworkX samples from G.nodes in insertion order) — an
    # unsorted edge frame would make net__betweenness non-reproducible
    # across runs/processes even with a fixed seed (Context.md §33).
    edges = edges.sort(["gene1", "gene2"])
    graph = nx.Graph()
    for gene1, gene2, score in edges.select("gene1", "gene2", "score").iter_rows():
        graph.add_edge(gene1, gene2, score=score)
    return graph


@cache
def _graph_wide_features(min_score: int, random_seed: int) -> pl.DataFrame:
    """Pagerank, sampled betweenness and dim__network for every gene, once.

    Pagerank and betweenness are whole-graph properties — computing them per
    disease would repeat identical, expensive work (module docstring).
    Cached per ``(min_score, random_seed)`` so a changed seed or threshold
    recomputes rather than silently reusing a stale estimate.

    :data:`DIMENSION_COLUMN` is a percentile rank of pagerank computed HERE,
    against the FULL graph population (~19.7k genes), not against whichever
    disease's smaller candidate set later calls :func:`build_network_features`.
    Ranking against the per-call candidate set instead would make an
    otherwise disease-invariant gene property (STRING topology doesn't know
    what disease is being scored) numerically depend on which disease's row
    you happen to read, and would shift systematically between a
    leave-one-disease-out fold's train and test populations — a modelling
    footgun XGBoost would silently inherit via ``select_feature_columns``.
    """
    graph = load_graph(min_score=min_score)
    pagerank = nx.pagerank(graph, weight="score")
    k = min(BETWEENNESS_SAMPLE_SIZE, graph.number_of_nodes())
    betweenness = nx.betweenness_centrality(graph, k=k, seed=random_seed)
    genes = list(graph.nodes)
    return pl.DataFrame(
        {
            "target_id": genes,
            PAGERANK_COLUMN: [pagerank[gene] for gene in genes],
            BETWEENNESS_COLUMN: [betweenness[gene] for gene in genes],
        }
    ).with_columns((pl.col(PAGERANK_COLUMN).rank(method="average") / len(genes)).alias(DIMENSION_COLUMN))


def build_network_features(
    gene_ids: list[str],
    config: FeaturesConfig | None = None,
    *,
    min_score: int = MEDIUM_CONFIDENCE,
) -> pl.DataFrame:
    """Derive network features. See ``groups.network`` in features.yaml.

    Args:
        gene_ids: Unversioned Ensembl gene IDs.
        config: Unused today; accepted for symmetry with other builders.
        min_score: STRING confidence threshold, forwarded to
            :func:`load_graph`. Record this if it's ever changed from the
            default (Context.md §33) — it changes the graph and therefore
            every feature here.

    Returns:
        ``target_id``, :data:`DEGREE_COLUMN`, :data:`WEIGHTED_DEGREE_COLUMN`,
        :data:`PAGERANK_COLUMN`, :data:`BETWEENNESS_COLUMN`,
        :data:`MEAN_CONFIDENCE_COLUMN`, :data:`DIMENSION_COLUMN`,
        :data:`MISSING_COLUMN`. A gene absent from the STRING graph at
        *min_score* gets a null across every feature column, never a zero
        (Context.md §32.3).
    """
    del config  # unused today; kept for call-site symmetry with other builders
    result_schema = {
        "target_id": pl.String,
        DEGREE_COLUMN: pl.UInt32,
        WEIGHTED_DEGREE_COLUMN: pl.Float64,
        MEAN_CONFIDENCE_COLUMN: pl.Float64,
        PAGERANK_COLUMN: pl.Float64,
        BETWEENNESS_COLUMN: pl.Float64,
        DIMENSION_COLUMN: pl.Float64,
        MISSING_COLUMN: pl.Int8,
    }
    if not gene_ids:
        return pl.DataFrame(schema=result_schema)

    graph = load_graph(min_score=min_score)
    random_seed = load_model_config().random_seed
    wide = _graph_wide_features(min_score, random_seed)

    rows = []
    for gene in gene_ids:
        if gene in graph:
            scores = [edge["score"] for edge in graph[gene].values()]
            rows.append(
                {
                    "target_id": gene,
                    DEGREE_COLUMN: len(scores),
                    WEIGHTED_DEGREE_COLUMN: float(sum(scores)),
                    MEAN_CONFIDENCE_COLUMN: float(sum(scores)) / len(scores) if scores else None,
                }
            )
        else:
            rows.append(
                {
                    "target_id": gene,
                    DEGREE_COLUMN: None,
                    WEIGHTED_DEGREE_COLUMN: None,
                    MEAN_CONFIDENCE_COLUMN: None,
                }
            )

    degree_frame = pl.DataFrame(
        rows,
        schema={
            "target_id": pl.String,
            DEGREE_COLUMN: pl.UInt32,
            WEIGHTED_DEGREE_COLUMN: pl.Float64,
            MEAN_CONFIDENCE_COLUMN: pl.Float64,
        },
    )
    # dim__network arrives already computed in `wide` (ranked against the
    # full graph population, not this call's candidate set — see
    # _graph_wide_features's docstring).
    result = degree_frame.join(wide, on="target_id", how="left")

    log_dropped(
        log,
        stage="network_coverage",
        reason=f"gene absent from the STRING graph at min_score={min_score}",
        count=result.filter(pl.col(DEGREE_COLUMN).is_null()).height,
        total=len(gene_ids),
    )

    return result.with_columns(pl.col(DEGREE_COLUMN).is_null().cast(pl.Int8).alias(MISSING_COLUMN))


def distance_to_disease_genes(
    graph: nx.Graph,
    gene_ids: list[str],
    disease_genes: list[str],
) -> pl.DataFrame:
    """Shortest-path distance from each gene to the nearest known disease gene.

    Genes in a disconnected component have no path. Record that as null with a
    missing indicator, not as infinity or a large sentinel — a sentinel becomes
    a real number to a tree model and invents an ordering.

    Not called by :func:`build_network_features` today (module docstring,
    milestone4_plan.md §2.1): solving "how do we get *disease_genes*" is a
    separate, deferred decision from whether this computation works.

    Args:
        graph: A graph from :func:`load_graph`.
        gene_ids: Genes to compute a distance for.
        disease_genes: Seed set of known disease genes. A gene present in
            both *gene_ids* and *disease_genes* trivially gets distance 0 to
            itself — callers doing guilt-by-association should exclude the
            candidate from *disease_genes* first (the same leave-one-out
            caveat as ``pathways.pathway_overlap_with_known_genes``).

    Returns:
        ``target_id``, :data:`MIN_DISTANCE_COLUMN` (nullable unsigned
        distance; null if the gene is absent from *graph* or unreachable
        from every seed).
    """
    result_schema = {"target_id": pl.String, MIN_DISTANCE_COLUMN: pl.UInt32}
    if not gene_ids:
        return pl.DataFrame(schema=result_schema)

    seeds = [gene for gene in disease_genes if gene in graph]
    if not seeds:
        return pl.DataFrame({"target_id": gene_ids}, schema={"target_id": pl.String}).with_columns(
            pl.lit(None, dtype=pl.UInt32).alias(MIN_DISTANCE_COLUMN)
        )

    # Multi-source BFS from every seed at once, rather than one BFS per
    # candidate gene — the distance to the NEAREST seed falls out directly.
    # weight=constant-1 makes this hop count, not confidence-weighted:
    # Context.md §14.5 asks for network DISTANCE, a topology property, not a
    # confidence-adjusted one (there's no un-weighted multi-source BFS
    # helper in this NetworkX version, so dijkstra with a unit weight
    # function stands in for one).
    distances = nx.multi_source_dijkstra_path_length(graph, seeds, weight=lambda *_: 1)

    rows = [{"target_id": gene, MIN_DISTANCE_COLUMN: distances.get(gene)} for gene in gene_ids]
    return pl.DataFrame(rows, schema=result_schema)
