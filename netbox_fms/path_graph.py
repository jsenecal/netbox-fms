"""Plant graph for fiber path analysis: a bulk loader and a linear walker.

Nodes are ports -- ``("fp", front_port_id)`` for a front port and
``("rp", rear_port_id, position)`` for one position of a rear port. Edges
are port mappings, cable crossings (rear ports paired by the rule shared
with the wizard) and splices. Every fiber is a chain: each node has at
most two fiber neighbours, so a walk is linear in path length. Components
that are not chains are quarantined as anomalies and not traced.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .choices import PathCompletenessChoices

NODE_FP = "fp"
NODE_RP = "rp"


def fp_node(fp_id):
    return (NODE_FP, fp_id)


def rp_node(rp_id, position):
    return (NODE_RP, rp_id, position)


def route_key_for(cable_ids):
    """sha256 hex of the ordered cable ids a path follows."""
    return hashlib.sha256(",".join(str(cable_id) for cable_id in cable_ids).encode()).hexdigest()


@dataclass(frozen=True)
class ChainEnd:
    """One classified end of a chain: the port it stops on (or None) and why."""

    port_id: int | None
    kind: str
    reason: str = ""


@dataclass
class Chain:
    """Ordered hops between two classified ends, as the walker emits them."""

    hops: list[tuple[str, int]]
    end_a: ChainEnd
    end_b: ChainEnd
    cable_ids: list[int]
    is_proposed: bool = False

    @property
    def completeness(self):
        return PathCompletenessChoices.from_end_kinds(self.end_a.kind, self.end_b.kind)

    @property
    def route_key(self):
        return route_key_for(self.cable_ids)

    @property
    def strand_ids(self):
        return [ref_id for kind, ref_id in self.hops if kind == "strand"]

    def reversed(self):
        return Chain(
            list(reversed(self.hops)), self.end_b, self.end_a, list(reversed(self.cable_ids)), self.is_proposed
        )


@dataclass(frozen=True)
class Anomaly:
    """A quarantined shape: the kind and the strand or front port it was found on."""

    kind: str
    strand_id: int | None = None
    front_port_id: int | None = None
