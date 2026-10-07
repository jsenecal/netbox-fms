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
from collections import Counter, defaultdict, namedtuple
from dataclasses import dataclass, field
from itertools import pairwise

import networkx as nx
from circuits.models import CircuitTermination
from dcim.choices import DeviceStatusChoices, LinkStatusChoices, PortTypeChoices
from dcim.models import Cable, CableTermination, Device, FrontPort, PortMapping, RearPort

from .choices import PathAnomalyKindChoices, PathCompletenessChoices, PathEndKindChoices, PathEndReasonChoices
from .models import FiberCable, FiberStrand
from .trace import paired_rear_port_terminations

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


# The end of a chain that stops short of any port: at a cable end, with nothing to name.
OPEN_CABLE_END = ChainEnd(None, PathEndKindChoices.OPEN, PathEndReasonChoices.CABLE_END)


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


FP_MODEL, RP_MODEL, CT_MODEL = "frontport", "rearport", "circuittermination"

# One cable termination as the loader reads it; `connector` and
# `termination_id` are what paired_rear_port_terminations consumes.
Term = namedtuple("Term", "model termination_id connector device_id")


@dataclass
class PlantGraph:
    """A loaded plant region: the port graph and the lookups the walker classifies ends with."""

    graph: nx.Graph = field(default_factory=nx.Graph)
    device_ids: set[int] = field(default_factory=set)
    device_fps: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    fp_type: dict[int, str] = field(default_factory=dict)
    fp_device: dict[int, int] = field(default_factory=dict)
    fp_at: dict[tuple[int, int], int] = field(default_factory=dict)
    rp_positions: dict[int, int] = field(default_factory=dict)
    fp_terminated: set[int] = field(default_factory=set)
    splice_fps: set[int] = field(default_factory=set)
    strand_by_fp: dict[int, int] = field(default_factory=dict)
    strand_ports: dict[int, tuple[int | None, int | None]] = field(default_factory=dict)
    strand_cable: dict[int, int] = field(default_factory=dict)
    strand_fiber_cable: dict[int, int] = field(default_factory=dict)
    fiber_cable_by_cable: dict[int, int] = field(default_factory=dict)
    cable_devices: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    sibling_fps: dict[tuple[int, int], set[int]] = field(default_factory=lambda: defaultdict(set))
    planned_cables: set[int] = field(default_factory=set)
    planned_devices: set[int] = field(default_factory=set)
    ct_circuit: dict[int, int] = field(default_factory=dict)
    other_ct: dict[int, int | None] = field(default_factory=dict)
    crossing_strands: set[int] = field(default_factory=set)
    anomalies: list[Anomaly] = field(default_factory=list)
    quarantined_nodes: set = field(default_factory=set)
    quarantined_strands: set[int] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_plant(seed_device_ids=None):
    """Load the plant region around the seed devices, or every fiber device when None.

    Expands device by device along cables: a device where a fiber can
    continue (it carries a front-port-to-front-port cable) is expanded, a
    device without one is loaded but not expanded, since every fiber stops
    there. Each expansion step is a handful of bulk queries.
    """
    plant = PlantGraph()
    cable_ids = _expand_region(plant, seed_device_ids)
    _load_ports(plant)
    terms_by_cable, ct_cable = _load_cables(plant, cable_ids)
    _load_strands(plant, cable_ids)
    _add_cable_edges(plant, terms_by_cable, ct_cable)
    _quarantine(plant)
    return plant


def _fiber_device_ids():
    """Every device terminating a cable that carries a FiberCable."""
    return set(
        CableTermination.objects.filter(cable__fiber_attributes__isnull=False, _device_id__isnull=False).values_list(
            "_device_id", flat=True
        )
    )


def _expand_region(plant, seed_device_ids):
    if seed_device_ids is None:
        from .path_analysis import device_ids_on_paths

        frontier = _fiber_device_ids() | device_ids_on_paths()
    else:
        frontier = set(seed_device_ids)
    cable_ids = set()
    while frontier:
        plant.device_ids |= frontier
        new_cables = set(CableTermination.objects.filter(_device_id__in=frontier).values_list("cable_id", flat=True))
        new_cables -= cable_ids
        new_cables |= _provider_span_cables(new_cables, cable_ids)
        cable_ids |= new_cables
        far = set(
            CableTermination.objects.filter(cable_id__in=new_cables, _device_id__isnull=False).values_list(
                "_device_id", flat=True
            )
        )
        far -= plant.device_ids
        plant.device_ids |= far
        frontier = _continuing_devices(far)
    # Front-port cables of every loaded device: splices continue fibers,
    # patches onto interfaces terminate them; both decide end kinds.
    cable_ids |= set(
        CableTermination.objects.filter(_device_id__in=plant.device_ids, termination_type__model=FP_MODEL).values_list(
            "cable_id", flat=True
        )
    )
    return cable_ids


def _continuing_devices(device_ids):
    """The devices among these that carry a front-port-to-front-port cable."""
    if not device_ids:
        return set()
    fp_terms = list(
        CableTermination.objects.filter(_device_id__in=device_ids, termination_type__model=FP_MODEL).values_list(
            "cable_id", "_device_id"
        )
    )
    fp_count = Counter(
        CableTermination.objects.filter(
            cable_id__in={cable_id for cable_id, _ in fp_terms}, termination_type__model=FP_MODEL
        ).values_list("cable_id", flat=True)
    )
    return {device_id for cable_id, device_id in fp_terms if fp_count[cable_id] >= 2}


def _provider_span_cables(cable_ids, known):
    """Cables beyond the provider circuits these cables land on, following chained circuits."""
    found, pending = set(), set(cable_ids)
    while pending:
        ct_ids = set(
            CableTermination.objects.filter(cable_id__in=pending, termination_type__model=CT_MODEL).values_list(
                "termination_id", flat=True
            )
        )
        if not ct_ids:
            break
        circuit_ids = CircuitTermination.objects.filter(pk__in=ct_ids).values("circuit_id")
        far_ct_ids = CircuitTermination.objects.filter(circuit_id__in=circuit_ids).values("pk")
        pending = set(
            CableTermination.objects.filter(
                termination_type__model=CT_MODEL, termination_id__in=far_ct_ids
            ).values_list("cable_id", flat=True)
        )
        pending -= cable_ids | known | found
        found |= pending
    return found


def _load_ports(plant):
    ids = plant.device_ids
    for pk, port_type, device_id in FrontPort.objects.filter(device_id__in=ids).values_list("pk", "type", "device_id"):
        plant.fp_type[pk] = port_type
        plant.fp_device[pk] = device_id
        plant.device_fps[device_id].append(pk)
    plant.rp_positions = dict(RearPort.objects.filter(device_id__in=ids).values_list("pk", "positions"))
    plant.planned_devices = set(
        Device.objects.filter(pk__in=ids, status=DeviceStatusChoices.STATUS_PLANNED).values_list("pk", flat=True)
    )
    mappings = PortMapping.objects.filter(device_id__in=ids).values_list(
        "front_port_id", "rear_port_id", "rear_port_position"
    )
    for fp, rp, position in mappings:
        plant.graph.add_edge(fp_node(fp), rp_node(rp, position), kind="mapping")
        plant.fp_at[(rp, position)] = fp


def _load_cables(plant, cable_ids):
    plant.planned_cables = set(
        Cable.objects.filter(pk__in=cable_ids, status=LinkStatusChoices.STATUS_PLANNED).values_list("pk", flat=True)
    )
    terms_by_cable = defaultdict(lambda: {"A": [], "B": []})
    ct_cable = {}
    rows = (
        CableTermination.objects.filter(cable_id__in=cable_ids)
        .order_by("pk")
        .values_list("cable_id", "cable_end", "termination_type__model", "termination_id", "connector", "_device_id")
    )
    for cable_id, end, model, termination_id, connector, device_id in rows:
        terms_by_cable[cable_id][end].append(Term(model, termination_id, connector, device_id))
        if device_id is not None:
            plant.cable_devices[cable_id].add(device_id)
        if model == CT_MODEL:
            ct_cable[termination_id] = (cable_id, end)
    circuit_ids = CircuitTermination.objects.filter(pk__in=list(ct_cable)).values("circuit_id")
    cts_by_circuit = defaultdict(list)
    for pk, circuit_id in CircuitTermination.objects.filter(circuit_id__in=circuit_ids).values_list("pk", "circuit_id"):
        plant.ct_circuit[pk] = circuit_id
        cts_by_circuit[circuit_id].append(pk)
    for pk, circuit_id in plant.ct_circuit.items():
        plant.other_ct[pk] = next((other for other in cts_by_circuit[circuit_id] if other != pk), None)
    return terms_by_cable, ct_cable


def _load_strands(plant, cable_ids):
    """Load the strands of the loaded cables and flag landings their cable never reaches.

    Strands of cables outside the loaded set are left out entirely: the
    region boundary says nothing about them, so they are neither traced nor
    quarantined.
    """
    plant.fiber_cable_by_cable = dict(FiberCable.objects.filter(cable_id__in=cable_ids).values_list("cable_id", "pk"))
    rows = list(
        FiberStrand.objects.filter(fiber_cable__cable_id__in=cable_ids).values_list(
            "pk", "fiber_cable_id", "fiber_cable__cable_id", "front_port_a_id", "front_port_b_id"
        )
    )
    unknown = {fp for *_, fp_a, fp_b in rows for fp in (fp_a, fp_b) if fp is not None and fp not in plant.fp_device}
    foreign_device = dict(FrontPort.objects.filter(pk__in=unknown).values_list("pk", "device_id"))
    for pk, fc_id, cable_id, fp_a, fp_b in rows:
        plant.strand_ports[pk] = (fp_a, fp_b)
        plant.strand_fiber_cable[pk] = fc_id
        plant.strand_cable[pk] = cable_id
        for fp in (fp_a, fp_b):
            if fp is None:
                continue
            plant.strand_by_fp[fp] = pk
            device_id = plant.fp_device.get(fp, foreign_device.get(fp))
            plant.sibling_fps[(fc_id, device_id)].add(fp)
            if device_id not in plant.cable_devices.get(cable_id, ()):
                # The strand says it lands here, but its cable never reaches this device.
                _quarantine_strand(plant, pk, PathAnomalyKindChoices.DANGLING_REFERENCE)


def _quarantine_strand(plant, strand_id, kind):
    if strand_id not in plant.quarantined_strands:
        plant.quarantined_strands.add(strand_id)
        plant.anomalies.append(Anomaly(kind, strand_id=strand_id))


def _add_cable_edges(plant, terms_by_cable, ct_cable):
    consumed = set()
    for cable_id in sorted(terms_by_cable):
        if cable_id in consumed:
            continue
        a, b = terms_by_cable[cable_id]["A"], terms_by_cable[cable_id]["B"]
        models_ = {term.model for term in a + b}
        if models_ == {FP_MODEL}:
            # A splice jumper or a patch cord: the fiber continues on the other front port.
            for term_a in a:
                for term_b in b:
                    plant.graph.add_edge(fp_node(term_a.termination_id), fp_node(term_b.termination_id), kind="splice")
                    plant.splice_fps.update((term_a.termination_id, term_b.termination_id))
            continue
        if FP_MODEL in models_:
            # A front port patched onto anything else (an interface) terminates the fiber.
            plant.fp_terminated.update(term.termination_id for term in a + b if term.model == FP_MODEL)
            continue
        rp_a = [term for term in a if term.model == RP_MODEL]
        rp_b = [term for term in b if term.model == RP_MODEL]
        if rp_a and rp_b:
            _add_crossings(plant, [("cable", cable_id)], rp_a, rp_b)
            continue
        for near, far in ((rp_a, b), (rp_b, a)):
            far_cts = [term for term in far if term.model == CT_MODEL]
            if near and far_cts:
                consumed |= _add_provider_crossings(plant, cable_id, near, far_cts[0], terms_by_cable, ct_cable)


def _add_provider_crossings(plant, cable_id, near_terms, ct_term, terms_by_cable, ct_cable):
    """Cross provider circuits from this cable's rear ports to the rear ports beyond.

    Hops each circuit end to end (recording the circuit and the cable on its
    far side) until a cable lands on rear ports; the provider span is
    opaque. Returns the cables consumed so the loop does not cross the span
    a second time from its other side.
    """
    segments = [("cable", cable_id)]
    consumed = set()
    ct_id = ct_term.termination_id
    while True:
        segments.append(("provider_circuit", plant.ct_circuit[ct_id]))
        egress = ct_cable.get(plant.other_ct[ct_id])
        if egress is None:
            return consumed
        egress_cable, egress_end = egress
        consumed.add(egress_cable)
        segments.append(("cable", egress_cable))
        far_terms = terms_by_cable[egress_cable]["B" if egress_end == "A" else "A"]
        far_rps = [term for term in far_terms if term.model == RP_MODEL]
        if far_rps:
            _add_crossings(plant, segments, near_terms, far_rps)
            return consumed
        far_cts = [term for term in far_terms if term.model == CT_MODEL]
        if not far_cts:
            return consumed
        ct_id = far_cts[0].termination_id


def _add_crossings(plant, segments, near_terms, far_terms):
    """One crossing edge per paired rear-port position, labelled with its hops."""
    cables = [ref_id for kind, ref_id in segments if kind == "cable"]
    for near_rp, far_rp in paired_rear_port_terminations(near_terms, far_terms):
        positions = min(plant.rp_positions[near_rp], plant.rp_positions[far_rp])
        for position in range(1, positions + 1):
            near, far = rp_node(near_rp, position), rp_node(far_rp, position)
            hops = _crossing_hops(plant, segments, near, far)
            if hops is not None:
                plant.graph.add_edge(near, far, kind="crossing", near=near, hops=hops, cables=cables)


def _crossing_hops(plant, segments, near, far):
    """The hops of one crossing: a strand where the cable carries a FiberCable, else the cable.

    Returns None when the strands landed on the two sides disagree; both are
    quarantined as dangling references.
    """
    hops = []
    last = len(segments) - 1
    for index, (kind, ref_id) in enumerate(segments):
        if kind != "cable" or ref_id not in plant.fiber_cable_by_cable:
            hops.append((kind, ref_id))
            continue
        strands = set()
        if index == 0:
            strands.add(plant.strand_by_fp.get(plant.fp_at.get((near[1], near[2]))))
        if index == last:
            strands.add(plant.strand_by_fp.get(plant.fp_at.get((far[1], far[2]))))
        strands.discard(None)
        if len(strands) > 1:
            for strand_id in strands:
                _quarantine_strand(plant, strand_id, PathAnomalyKindChoices.DANGLING_REFERENCE)
            return None
        if strands:
            (strand_id,) = strands
            plant.crossing_strands.add(strand_id)
            hops.append(("strand", strand_id))
        else:
            hops.append(("cable", ref_id))
    return hops


def _quarantine(plant):
    """Record anomalies and take their components out of the walk.

    A strand landed on both ends that got no crossing edge disagrees with
    the plant it claims to cross (an ambiguous or missing far end), so it
    is a dangling reference. Then every component that is not a chain --
    a branching node or a cycle -- is quarantined whole.
    """
    graph = plant.graph
    for strand_id, (fp_a, fp_b) in plant.strand_ports.items():
        if fp_a is not None and fp_b is not None and strand_id not in plant.crossing_strands:
            _quarantine_strand(plant, strand_id, PathAnomalyKindChoices.DANGLING_REFERENCE)
    for u, v, data in list(graph.edges(data=True)):
        if data["kind"] == "crossing" and plant.quarantined_strands.intersection(_edge_strands(data)):
            graph.remove_edge(u, v)
    plant.crossing_strands -= plant.quarantined_strands
    for component in nx.connected_components(graph):
        subgraph = graph.subgraph(component)
        branching = sorted(node for node in component if _is_branching(graph, node))
        if not branching and subgraph.number_of_edges() < len(component):
            continue
        strands = sorted(
            {
                strand_id
                for _u, _v, data in subgraph.edges(data=True)
                if data["kind"] == "crossing"
                for strand_id in _edge_strands(data)
            }
        )
        if branching:
            # Only a front port can branch: the database allows a rear-port position one mapping.
            plant.anomalies.extend(
                Anomaly(PathAnomalyKindChoices.TOO_MANY_CONNECTIONS, front_port_id=node[1]) for node in branching
            )
        elif strands:
            plant.anomalies.extend(Anomaly(PathAnomalyKindChoices.LOOP, strand_id=s) for s in strands)
        else:
            lowest_fp = min(node[1] for node in component if node[0] == NODE_FP)
            plant.anomalies.append(Anomaly(PathAnomalyKindChoices.LOOP, front_port_id=lowest_fp))
        plant.quarantined_nodes |= component
        plant.quarantined_strands |= set(strands)
        plant.crossing_strands -= set(strands)


def _is_branching(graph, node):
    """More than two neighbours, or a front port mapped to more than one rear-port position."""
    if graph.degree(node) > 2:
        return True
    return node[0] == NODE_FP and sum(1 for *_, data in graph.edges(node, data=True) if data["kind"] == "mapping") > 1


def _edge_strands(data):
    return [ref_id for kind, ref_id in data["hops"] if kind == "strand"]


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------


def classify_end(plant, node):
    """Terminated for a non-splice port or one patched onto an interface; open otherwise."""
    if node[0] != NODE_FP:
        return OPEN_CABLE_END
    fp = node[1]
    if plant.fp_type.get(fp) != PortTypeChoices.TYPE_SPLICE or fp in plant.fp_terminated:
        return ChainEnd(fp, PathEndKindChoices.TERMINATED, "")
    return ChainEnd(fp, PathEndKindChoices.OPEN, _open_reason(plant, fp))


def _open_reason(plant, fp):
    """Unspliced when a sibling fiber of the same cable is spliced in this closure, else a cable end."""
    strand_id = plant.strand_by_fp.get(fp)
    if strand_id is not None:
        siblings = plant.sibling_fps.get((plant.strand_fiber_cable[strand_id], plant.fp_device.get(fp)), ())
        if any(sibling != fp and sibling in plant.splice_fps for sibling in siblings):
            return PathEndReasonChoices.UNSPLICED
    return PathEndReasonChoices.CABLE_END


def _is_proposed(plant, cable_ids, end_nodes):
    if any(cable_id in plant.planned_cables for cable_id in cable_ids):
        return True
    return any(node[0] == NODE_FP and plant.fp_device.get(node[1]) in plant.planned_devices for node in end_nodes)


def walk_from(plant, node):
    """The chains through this port: one for a fiber, none for a fiberless port, one per half-landed strand."""
    graph = plant.graph
    if node in plant.quarantined_nodes:
        return []
    component = nx.node_connected_component(graph, node) if node in graph else {node}
    if not any(data["kind"] == "crossing" for _u, _v, data in graph.subgraph(component).edges(data=True)):
        return _half_landed_chains(plant, component)
    a, b = sorted(n for n in component if graph.degree(n) <= 1)
    hops, cables = [], []
    for u, v in pairwise(nx.shortest_path(graph, a, b)):
        data = graph.edges[u, v]
        if data["kind"] != "crossing":
            continue
        forward = data["near"] == u
        hops.extend(data["hops"] if forward else reversed(data["hops"]))
        cables.extend(data["cables"] if forward else reversed(data["cables"]))
    return [Chain(hops, classify_end(plant, a), classify_end(plant, b), cables, _is_proposed(plant, cables, (a, b)))]


def _half_landed_chains(plant, component):
    """Strands landed on a port of this fiberless component whose crossing could not be resolved."""
    chains = []
    for node in sorted(component):
        strand_id = plant.strand_by_fp.get(node[1]) if node[0] == NODE_FP else None
        if strand_id is None or strand_id in plant.crossing_strands or strand_id in plant.quarantined_strands:
            continue
        cable_id = plant.strand_cable[strand_id]
        chains.append(
            Chain(
                [("strand", strand_id)],
                classify_end(plant, node),
                OPEN_CABLE_END,
                [cable_id],
                _is_proposed(plant, [cable_id], (node,)),
            )
        )
    return chains


def orphan_chains(plant):
    """Single-hop chains for strands that land on no port at all: open at both ends, no port."""
    return [
        Chain(
            [("strand", strand_id)],
            OPEN_CABLE_END,
            OPEN_CABLE_END,
            [plant.strand_cable[strand_id]],
            plant.strand_cable[strand_id] in plant.planned_cables,
        )
        for strand_id, (fp_a, fp_b) in sorted(plant.strand_ports.items())
        if fp_a is None and fp_b is None
    ]


def walk_nodes(plant, nodes):
    """The chains reached from these start nodes, each fiber component walked once, plus the port-less strands.

    A strand landed on a port with no place in the graph (no mapping, no
    cable) is walked from that port like any other start node.
    """
    chains, seen = [], set()
    for node in nodes:
        if node in seen:
            continue
        if node in plant.graph:
            seen |= nx.node_connected_component(plant.graph, node)
        chains.extend(walk_from(plant, node))
    chains.extend(orphan_chains(plant))
    return chains


def walk_all(plant):
    """Every chain of the loaded plant: one per fiber component plus the strands that land on no graph node."""
    landed = {fp_node(fp_id) for fp_id in plant.strand_by_fp}
    return walk_nodes(plant, sorted(set(plant.graph.nodes) | landed))
