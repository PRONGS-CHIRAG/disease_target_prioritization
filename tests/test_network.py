"""Tests for network features (Context.md §14.5, §18.1, Milestone 4).

A small hand-built graph rather than the real ~930k-edge STRING network:

    A --(900)-- B --(400)-- C        D --(500)-- E   (isolated pair)

    A: neighbours {B}         degree 1, weighted 900
    B: neighbours {A, C}      degree 2, weighted 1300
    C: neighbours {B}         degree 1, weighted 400
    D: neighbours {E}         degree 1, weighted 500 (separate component from A/B/C)
    F: not in the graph at all
"""

from __future__ import annotations

import networkx as nx
import polars as pl
import pytest

from target_prioritization.features import network


@pytest.fixture
def graph() -> nx.Graph:
    g = nx.Graph()
    g.add_edge("A", "B", score=900)
    g.add_edge("B", "C", score=400)
    g.add_edge("D", "E", score=500)
    return g


def _patch(monkeypatch, graph: nx.Graph, random_seed: int = 42) -> None:
    monkeypatch.setattr(network, "load_graph", lambda min_score=network.MEDIUM_CONFIDENCE: graph)
    monkeypatch.setattr(
        network, "load_model_config", lambda: type("Cfg", (), {"random_seed": random_seed})()
    )


class TestBuildNetworkFeatures:
    def test_degree_and_weighted_degree(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["A", "B", "C"])
        by_gene = {row["target_id"]: row for row in result.iter_rows(named=True)}
        assert by_gene["A"][network.DEGREE_COLUMN] == 1
        assert by_gene["A"][network.WEIGHTED_DEGREE_COLUMN] == 900.0
        assert by_gene["B"][network.DEGREE_COLUMN] == 2
        assert by_gene["B"][network.WEIGHTED_DEGREE_COLUMN] == 1300.0

    def test_mean_edge_confidence(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["B"])
        row = result.row(0, named=True)
        assert row[network.MEAN_CONFIDENCE_COLUMN] == 650.0  # mean(900, 400)

    def test_gene_absent_from_graph_is_null_not_zero(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["F"])
        row = result.row(0, named=True)
        assert row[network.DEGREE_COLUMN] is None
        assert row[network.WEIGHTED_DEGREE_COLUMN] is None
        assert row[network.MEAN_CONFIDENCE_COLUMN] is None
        assert row[network.PAGERANK_COLUMN] is None
        assert row[network.MISSING_COLUMN] == 1

    def test_present_gene_is_not_flagged_missing(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["A"])
        assert result.row(0, named=True)[network.MISSING_COLUMN] == 0

    def test_pagerank_and_betweenness_are_populated_for_present_genes(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["A", "B", "C", "D", "E"])
        assert result.get_column(network.PAGERANK_COLUMN).null_count() == 0
        assert result.get_column(network.BETWEENNESS_COLUMN).null_count() == 0
        # B is the bridge in its component; A and C are leaves.
        by_gene = {row["target_id"]: row for row in result.iter_rows(named=True)}
        assert by_gene["B"][network.BETWEENNESS_COLUMN] > by_gene["A"][network.BETWEENNESS_COLUMN]

    def test_every_requested_gene_gets_exactly_one_row(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features(["A", "B", "C", "D", "E", "F"])
        assert result.height == 6

    def test_empty_input_returns_correctly_typed_empty_frame(self, monkeypatch, graph):
        _patch(monkeypatch, graph)
        result = network.build_network_features([])
        assert result.height == 0
        assert result.schema["target_id"] == pl.String
        assert result.schema[network.DEGREE_COLUMN] == pl.UInt32

    def test_dim_network_does_not_depend_on_the_calling_candidate_set(self, monkeypatch, graph):
        """dim__network must rank against the FULL graph population, not
        whichever subset of genes this particular call happens to request —
        otherwise the same, disease-invariant STRING topology would score
        differently depending on which disease's candidate set asked for it
        (a leave-one-disease-out train/test population-size mismatch)."""
        _patch(monkeypatch, graph)
        network._graph_wide_features.cache_clear()
        alone = network.build_network_features(["B"])
        network._graph_wide_features.cache_clear()
        with_everyone = network.build_network_features(["A", "B", "C", "D", "E"])
        b_alone = alone.row(0, named=True)[network.DIMENSION_COLUMN]
        b_with_everyone = with_everyone.filter(pl.col("target_id") == "B").row(0, named=True)[
            network.DIMENSION_COLUMN
        ]
        assert b_alone == b_with_everyone

    def test_betweenness_is_reproducible_given_the_same_seed(self, monkeypatch, graph):
        """Sampled betweenness (module docstring, milestone4_plan.md §2.2)
        must be deterministic for a fixed seed — Context.md §33."""
        _patch(monkeypatch, graph, random_seed=7)
        first = network.build_network_features(["A", "B", "C"])
        network._graph_wide_features.cache_clear()
        _patch(monkeypatch, graph, random_seed=7)
        second = network.build_network_features(["A", "B", "C"])
        assert first[network.BETWEENNESS_COLUMN].to_list() == second[network.BETWEENNESS_COLUMN].to_list()


class TestLoadGraphIsOrderIndependent:
    def test_graph_node_order_is_independent_of_edge_row_order(self, monkeypatch):
        """``load_gene_level_edges`` ends in a polars ``group_by``, which
        gives no row-order guarantee. ``load_graph`` must sort before
        inserting into the graph — otherwise net__betweenness's k=500
        sample (NetworkX draws it from ``G.nodes`` in INSERTION order)
        would silently differ across runs/processes even with a fixed
        seed, breaking Context.md §33 reproducibility."""
        edges_a = pl.DataFrame(
            {"gene1": ["A", "C", "B"], "gene2": ["B", "D", "C"], "score": [900, 200, 400]}
        )
        edges_b = edges_a.reverse()  # identical rows, reversed order

        report = type("FakeReport", (), {"log": lambda self: None})()

        network.load_graph.cache_clear()
        monkeypatch.setattr(network, "load_gene_level_edges", lambda min_score: (edges_a, report))
        order_a = list(network.load_graph(min_score=400).nodes)

        network.load_graph.cache_clear()
        monkeypatch.setattr(network, "load_gene_level_edges", lambda min_score: (edges_b, report))
        order_b = list(network.load_graph(min_score=400).nodes)

        assert order_a == order_b


class TestDistanceToDiseaseGenes:
    def test_seed_gene_has_distance_zero_to_itself(self, graph):
        result = network.distance_to_disease_genes(graph, ["A"], disease_genes=["A"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] == 0

    def test_direct_neighbour_has_distance_one(self, graph):
        result = network.distance_to_disease_genes(graph, ["B"], disease_genes=["A"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] == 1

    def test_two_hops_away(self, graph):
        result = network.distance_to_disease_genes(graph, ["C"], disease_genes=["A"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] == 2

    def test_disconnected_component_is_null_not_infinity(self, graph):
        """D and E share no edge path to A/B/C at all."""
        result = network.distance_to_disease_genes(graph, ["D"], disease_genes=["A"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] is None

    def test_takes_the_nearest_of_multiple_seeds(self, graph):
        result = network.distance_to_disease_genes(graph, ["C"], disease_genes=["A", "B"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] == 1

    def test_gene_absent_from_graph_is_null(self, graph):
        result = network.distance_to_disease_genes(graph, ["F"], disease_genes=["A"])
        assert result.row(0, named=True)[network.MIN_DISTANCE_COLUMN] is None

    def test_no_valid_seeds_returns_all_null(self, graph):
        result = network.distance_to_disease_genes(graph, ["A", "B"], disease_genes=["not_in_graph"])
        assert result.get_column(network.MIN_DISTANCE_COLUMN).null_count() == 2

    def test_empty_gene_ids_returns_correctly_typed_empty_frame(self, graph):
        result = network.distance_to_disease_genes(graph, [], disease_genes=["A"])
        assert result.height == 0
        assert result.schema["target_id"] == pl.String
