"""Generate draw.io (mxGraph XML) diagrams for splice plans."""

import xml.etree.ElementTree as ET

from dcim.models import FrontPort, Module

from netbox_fms.models import FiberStrand

from .services import UNASSIGNED_TRAY_ID, compute_diff

EMPTY_DIFF = {"add": [], "remove": [], "unchanged": []}


def _add_page(mxfile, name, header_text, ports, page_diff):
    """Render one diagram page: a header, the ports, and the diff edges."""
    diagram = ET.SubElement(mxfile, "diagram", name=name)

    model = ET.SubElement(diagram, "mxGraphModel")
    root = ET.SubElement(model, "root")

    # Required mxGraph root cells
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    # Layout: ports as nodes, connections drawn between pairs
    y_offset = 40
    cell_id = 2
    port_cells = {}

    # Header
    header = ET.SubElement(
        root,
        "mxCell",
        id=str(cell_id),
        value=header_text,
        style="text;fontStyle=1;fontSize=14",
        vertex="1",
        parent="1",
    )
    ET.SubElement(header, "mxGeometry", x="10", y="10", width="400", height="20", **{"as": "geometry"})
    cell_id += 1

    # Look up fiber strand colors via FiberStrand.front_port_a FK
    strand_colors = dict(FiberStrand.objects.filter(front_port_a__in=ports).values_list("front_port_a_id", "color"))

    for port in ports:
        color = f"#{strand_colors[port.pk]}" if port.pk in strand_colors else "#CCCCCC"
        style = f"rounded=1;fillColor={color};fontColor=#000000;strokeColor=#333333"

        cell = ET.SubElement(root, "mxCell", id=str(cell_id), value=port.name, style=style, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x="20", y=str(y_offset), width="120", height="24", **{"as": "geometry"})
        port_cells[port.pk] = str(cell_id)
        cell_id += 1
        y_offset += 30

    # Draw connections
    edges = [
        *[(p, "#000000", "") for p in page_diff["unchanged"]],
        *[(p, "#00CC00", "dashed=1") for p in page_diff["add"]],
        *[(p, "#CC0000", "dashed=1") for p in page_diff["remove"]],
    ]
    for pair, edge_color, style_extra in edges:
        pa, pb = pair
        src = port_cells.get(pa)
        tgt = port_cells.get(pb)
        if src and tgt:
            style = f"strokeColor={edge_color};strokeWidth=2;{style_extra}"
            ET.SubElement(
                root,
                "mxCell",
                id=str(cell_id),
                style=style,
                edge="1",
                parent="1",
                source=src,
                target=tgt,
            )
            cell_id += 1


def generate_drawio(plan):
    """
    Generate a draw.io XML file for a splice plan.
    One page/tab per tray, plus an "Unassigned tubes" page when the diff
    carries splices on device-level ports (tubes not assigned to any tray).
    Fibers colored by each strand's stored color (assigned from the cable
    type's color scheme), diff annotations.
    """
    diff = compute_diff(plan)

    mxfile = ET.Element("mxfile", host="netbox-fms")

    trays = Module.objects.filter(device=plan.closure).order_by("module_bay__name")
    pages = [
        (
            f"Tray: {tray}",
            f"Tray: {tray}",
            FrontPort.objects.filter(device=plan.closure, module=tray).order_by("name"),
            diff.get(tray.pk, EMPTY_DIFF),
        )
        for tray in trays
    ]

    # The unassigned bucket is not a tray: it gets its own page listing only
    # the ports its pairs touch (every device-level port of a closure would
    # be far too many), flagged as an inconsistency in the header.
    unassigned_diff = diff.get(UNASSIGNED_TRAY_ID) or EMPTY_DIFF
    unassigned_port_ids = {p for pairs in unassigned_diff.values() for pair in pairs for p in pair}
    if unassigned_port_ids:
        pages.append(
            (
                "Unassigned tubes",
                "Unassigned tubes (splices on tubes not assigned to any tray)",
                FrontPort.objects.filter(pk__in=unassigned_port_ids).order_by("name"),
                unassigned_diff,
            )
        )

    if not pages:
        # Empty diagram
        diagram = ET.SubElement(mxfile, "diagram", name=plan.name)
        model = ET.SubElement(diagram, "mxGraphModel")
        ET.SubElement(model, "root")
        return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)

    for name, header_text, ports, page_diff in pages:
        _add_page(mxfile, name, header_text, ports, page_diff)

    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)
