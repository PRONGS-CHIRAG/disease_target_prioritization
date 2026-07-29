"""Identifier normalization.

Context.md §12 calls this "one of the most important data-engineering tasks",
and §32.6 lists identifier errors among the top risks: a bad mapping invents a
disease-gene association that no database actually asserts, and nothing
downstream will flag it.

The internal key is the **Ensembl gene ID** (Context.md §12). Every source
below reaches it differently, and each has a specific trap:

===========  ====================================  ==================================
Source       Native key                            Trap
===========  ====================================  ==================================
GTEx         ``ENSG00000186092.7``                 version suffix breaks equality
STRING       ``9606.ENSP00000493376``              protein ID, not gene ID
Reactome     ``ENSG00000186092``                   multi-species in one file
HGNC         ``BRCA1``                             symbols get retired and reused
===========  ====================================  ==================================

Every function here reports what it could not map rather than dropping it
silently (Context.md §34).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import polars as pl

from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "ENSEMBL_GENE_RE",
    "ENSEMBL_PROTEIN_RE",
    "MappingReport",
    "build_symbol_lookup",
    "ensp_to_ensg_from_string_aliases",
    "filter_reactome_to_human",
    "is_ensembl_gene_id",
    "normalize_ensembl_id",
    "strip_ensembl_version",
]

log = get_logger(__name__)

# Ensembl human gene IDs: ENSG + 11 digits. Optional `.N` version suffix.
ENSEMBL_GENE_RE = re.compile(r"^ENSG\d{11}(\.\d+)?$")
ENSEMBL_PROTEIN_RE = re.compile(r"^(?:\d+\.)?ENSP\d{11}(\.\d+)?$")

REACTOME_HUMAN_SPECIES = "Homo sapiens"
STRING_HUMAN_TAXON = "9606"


@dataclass(slots=True)
class MappingReport:
    """Outcome of a mapping step.

    Context.md §32.6 requires unresolved records to be reported. Returning this
    alongside the mapped frame makes the unmapped count impossible to ignore.
    """

    stage: str
    total: int = 0
    mapped: int = 0
    unmapped_examples: list[str] = field(default_factory=list)

    @property
    def unmapped(self) -> int:
        return self.total - self.mapped

    @property
    def mapped_fraction(self) -> float:
        return self.mapped / self.total if self.total else 0.0

    def log(self) -> None:
        log_dropped(
            log,
            stage=self.stage,
            reason="identifier could not be mapped to an Ensembl gene ID",
            count=self.unmapped,
            total=self.total,
            examples=self.unmapped_examples,
        )

    def __str__(self) -> str:
        return (
            f"{self.stage}: {self.mapped:,}/{self.total:,} mapped "
            f"({self.mapped_fraction:.1%}), {self.unmapped:,} unmapped"
        )


# ---------------------------------------------------------------------------
# Ensembl gene IDs
# ---------------------------------------------------------------------------


def strip_ensembl_version(gene_id: str | None) -> str | None:
    """Drop the ``.N`` version suffix from an Ensembl ID.

    GTEx ships versioned IDs (``ENSG00000186092.7``) while Open Targets and
    Reactome use unversioned ones. Joining the two without stripping yields
    zero matches — and, worse, a *silent* zero: an empty inner join looks like
    "this gene has no expression data" rather than a bug.

    Only a trailing ``.<digits>`` is removed, so identifiers that legitimately
    contain a dot are left alone.

    >>> strip_ensembl_version("ENSG00000186092.7")
    'ENSG00000186092'
    >>> strip_ensembl_version("ENSG00000186092")
    'ENSG00000186092'
    >>> strip_ensembl_version(None) is None
    True
    """
    if gene_id is None:
        return None
    gene_id = gene_id.strip()
    if not gene_id:
        return None
    base, sep, suffix = gene_id.rpartition(".")
    if sep and suffix.isdigit() and base:
        return base
    return gene_id


def normalize_ensembl_id(gene_id: str | None) -> str | None:
    """Uppercase, strip whitespace and remove the version suffix."""
    if gene_id is None:
        return None
    cleaned = strip_ensembl_version(gene_id.strip().upper())
    return cleaned or None


def is_ensembl_gene_id(value: str | None) -> bool:
    """True if *value* looks like a human Ensembl gene ID.

    >>> is_ensembl_gene_id("ENSG00000186092")
    True
    >>> is_ensembl_gene_id("ENSP00000493376")
    False
    """
    return bool(value) and bool(ENSEMBL_GENE_RE.match(str(value).strip().upper()))


def strip_ensembl_version_expr(column: str) -> pl.Expr:
    """Polars expression form of :func:`strip_ensembl_version`.

    Used in frame pipelines where a Python-level ``map_elements`` would be
    orders of magnitude slower — GTEx has ~60k genes, STRING ~13M edges.
    """
    return (
        pl.col(column).str.strip_chars().str.to_uppercase().str.replace(r"\.\d+$", "").alias(column)
    )


# ---------------------------------------------------------------------------
# STRING: ENSP -> ENSG
# ---------------------------------------------------------------------------


def ensp_to_ensg_from_string_aliases(
    aliases: pl.DataFrame | pl.LazyFrame,
) -> tuple[pl.DataFrame, MappingReport]:
    """Build a STRING protein ID → Ensembl gene ID lookup.

    STRING keys its interaction network on Ensembl *protein* IDs prefixed with
    the taxon (``9606.ENSP00000493376``), so the edge list cannot be joined to
    anything gene-keyed without this bridge. The aliases file carries the
    mapping under sources such as ``Ensembl_gene`` or ``Ensembl_HGNC_ensembl_gene_id``.

    Because a gene can encode several protein isoforms, this map is
    many-to-one: several ENSPs collapse to one ENSG. That is expected — network
    features are aggregated per gene afterwards.

    Args:
        aliases: Parsed ``9606.protein.aliases.v12.0.txt.gz`` with columns
            ``string_protein_id``, ``alias``, ``source``.

    Returns:
        ``(lookup, report)`` where *lookup* has columns ``string_protein_id``
        and ``ensembl_gene_id``.
    """
    frame = aliases.lazy()

    lookup = (
        frame.filter(pl.col("alias").str.to_uppercase().str.contains(r"^ENSG\d{11}"))
        .with_columns(
            pl.col("alias")
            .str.strip_chars()
            .str.to_uppercase()
            .str.replace(r"\.\d+$", "")
            .alias("ensembl_gene_id")
        )
        .filter(pl.col("ensembl_gene_id").str.contains(r"^ENSG\d{11}$"))
        .select("string_protein_id", "ensembl_gene_id")
        .unique()
        .collect()
    )

    all_proteins = frame.select("string_protein_id").unique().collect()
    total = all_proteins.height
    mapped = lookup.select("string_protein_id").unique().height

    unmapped_examples = (
        all_proteins.join(
            lookup.select("string_protein_id").unique(), on="string_protein_id", how="anti"
        )
        .head(5)
        .get_column("string_protein_id")
        .to_list()
    )

    report = MappingReport(
        stage="string_ensp_to_ensg",
        total=total,
        mapped=mapped,
        unmapped_examples=unmapped_examples,
    )
    report.log()
    return lookup, report


# ---------------------------------------------------------------------------
# Reactome
# ---------------------------------------------------------------------------


def filter_reactome_to_human(
    mapping: pl.DataFrame | pl.LazyFrame,
    *,
    species_column: str = "species",
    gene_column: str = "ensembl_gene_id",
) -> tuple[pl.DataFrame, MappingReport]:
    """Restrict ``Ensembl2Reactome_All_Levels.txt`` to human genes.

    That file covers every species Reactome has inferred pathways for — mouse,
    rat, zebrafish and more. Without the species filter, a mouse gene whose
    Ensembl ID happens to be well-formed contributes pathway counts to a human
    target. The rows are dropped by *species*, then the surviving IDs are
    checked against the human ``ENSG`` pattern as a second, independent guard.

    Args:
        mapping: Parsed Reactome mapping frame.
        species_column: Column holding the species name.
        gene_column: Column holding the Ensembl gene ID.

    Returns:
        ``(human_rows, report)``.
    """
    frame = mapping.lazy()
    total = frame.select(pl.len()).collect().item()

    human = (
        frame.filter(pl.col(species_column) == REACTOME_HUMAN_SPECIES)
        .with_columns(strip_ensembl_version_expr(gene_column))
        .filter(pl.col(gene_column).str.contains(r"^ENSG\d{11}$"))
        .collect()
    )

    dropped_examples = (
        frame.filter(pl.col(species_column) != REACTOME_HUMAN_SPECIES)
        .select(species_column)
        .unique()
        .head(5)
        .collect()
        .get_column(species_column)
        .to_list()
    )

    report = MappingReport(
        stage="reactome_human_filter",
        total=total,
        mapped=human.height,
        unmapped_examples=dropped_examples,
    )
    report.log()
    return human, report


# ---------------------------------------------------------------------------
# HGNC symbols
# ---------------------------------------------------------------------------


def build_symbol_lookup(
    hgnc: pl.DataFrame | pl.LazyFrame,
    *,
    symbol_column: str = "symbol",
    ensembl_column: str = "ensembl_gene_id",
    prev_symbol_column: str = "prev_symbol",
    alias_symbol_column: str = "alias_symbol",
) -> tuple[pl.DataFrame, MappingReport]:
    """Build a gene-symbol → Ensembl gene ID lookup including historical names.

    Gene symbols are display labels, not stable keys: they get renamed
    (``PARK2`` → ``PRKN``), and a retired symbol can later be reassigned to a
    different gene. Matching on the current symbol alone silently loses every
    record written under an older name — a real problem here, since Parkinson's
    literature uses ``PARK2`` and ``PARK7`` extensively.

    HGNC packs previous and alias symbols into pipe-delimited fields, so both
    are exploded into their own rows.

    The resulting lookup is deliberately **ambiguity-aware**: the ``priority``
    column ranks approved symbols above previous ones above aliases, so a
    caller resolving a collision has a defensible rule rather than whichever
    row happened to sort first.

    Returns:
        ``(lookup, report)`` with columns ``symbol``, ``ensembl_gene_id``,
        ``symbol_kind`` and ``priority``.
    """
    frame = hgnc.lazy().filter(
        pl.col(ensembl_column).is_not_null() & (pl.col(ensembl_column) != "")
    )

    def _explode(column: str, kind: str, priority: int) -> pl.LazyFrame:
        if column not in frame.collect_schema().names():
            return pl.LazyFrame(
                schema={
                    "symbol": pl.String,
                    "ensembl_gene_id": pl.String,
                    "symbol_kind": pl.String,
                    "priority": pl.Int32,
                }
            )
        return (
            frame.select(
                pl.col(column).alias("symbol"),
                pl.col(ensembl_column).alias("ensembl_gene_id"),
            )
            .filter(pl.col("symbol").is_not_null() & (pl.col("symbol") != ""))
            # HGNC uses "|" to pack multiple values into one field.
            .with_columns(pl.col("symbol").str.split("|"))
            # empty_as_null pinned explicitly: the Polars 2.0 default flips,
            # and an implicit change here would alter which rows survive.
            .explode("symbol", empty_as_null=False)
            .with_columns(
                pl.col("symbol").str.strip_chars().str.to_uppercase(),
                pl.col("ensembl_gene_id").str.strip_chars().str.to_uppercase(),
                pl.lit(kind).alias("symbol_kind"),
                pl.lit(priority, dtype=pl.Int32).alias("priority"),
            )
            .filter(pl.col("symbol") != "")
        )

    lookup = (
        pl.concat(
            [
                _explode(symbol_column, "approved", 0),
                _explode(prev_symbol_column, "previous", 1),
                _explode(alias_symbol_column, "alias", 2),
            ],
            how="vertical",
        )
        .unique(subset=["symbol", "ensembl_gene_id", "symbol_kind"])
        .sort("priority")
        .collect()
    )

    total = frame.select(pl.len()).collect().item()
    ambiguous = (
        lookup.group_by("symbol")
        .agg(pl.col("ensembl_gene_id").n_unique().alias("n"))
        .filter(pl.col("n") > 1)
    )
    if ambiguous.height:
        log.info(
            "ambiguous_symbols",
            stage="hgnc_symbol_lookup",
            count=ambiguous.height,
            note="symbols mapping to multiple genes; resolve using the priority column",
            examples=ambiguous.head(5).get_column("symbol").to_list(),
        )

    report = MappingReport(
        stage="hgnc_symbol_lookup",
        total=total,
        mapped=lookup.select("ensembl_gene_id").unique().height,
    )
    report.log()
    return lookup, report
