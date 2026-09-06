"""Pure paper-native affiliation identifier alignment, shared across adapters.

No acquisition, certification artifact writers or validation runners belong here.
"""


def align_affiliation_ror_evidence(
    *,
    local_rors: tuple[str, ...],
    author_rors: tuple[str, ...],
    affiliation_count: int,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """Align author-level RORs only when there is exactly one affiliation.

    INSPIRE's ``affiliations_identifiers`` is attached to the author rather
    than to an individual affiliation row. It may corroborate the one row of
    a single-affiliation author, but it cannot be positionally distributed
    across multiple rows. A disagreement in the single-row case is retained
    as explicit conflicting evidence and must never certify either target.
    """

    if affiliation_count < 1:
        raise ValueError("affiliation count must be positive")
    local = tuple(sorted(set(local_rors)))
    author = tuple(sorted(set(author_rors)))
    if affiliation_count > 1:
        if local and author:
            return (
                local,
                "affiliation-local-ror-author-level-set-unaligned",
                (),
            )
        if local:
            return local, "affiliation-local-ror", ()
        if author:
            return (), "unresolved-author-ror-not-positionally-aligned", ()
        return (), "no-ror-evidence", ()

    if local and author:
        if local == author:
            return local, "single-affiliation-local-author-ror-corroborated", ()
        return (
            tuple(sorted(set(local) | set(author))),
            "conflicted-single-affiliation-local-vs-author-ror",
            ("single-affiliation local and author-level ROR identifier sets disagree",),
        )
    if local:
        return local, "affiliation-local-ror", ()
    if author:
        if len(author) == 1:
            return author, "single-affiliation-author-ror", ()
        return (
            author,
            "conflicted-single-affiliation-multiple-author-rors",
            (
                "one affiliation row has multiple author-level ROR targets and "
                "cannot be resolved to one institution",
            ),
        )
    return (), "no-ror-evidence", ()
