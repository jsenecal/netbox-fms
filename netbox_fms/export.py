"""Generate draw.io (mxGraph XML) diagrams for splice plans."""

import xml.etree.ElementTree as ET

from .services import compute_diff


def generate_drawio(plan):
    """
    Generate a draw.io XML file for a splice plan.
    One page/tab per tray. Fibers colored by EIA-598, diff annotations.
    """
    diff = compute_diff(plan)

    mxfile = ET.Element("mxfile", host="netbox-fms")

    from dcim.models import FrontPort, Module

    trays = Module.objects.filter(device=plan.closure).order_by("module_bay__name")

    if not trays.exists():
        # Empty diagram
        diagram = ET.SubElement(mxfile, "diagram", name=plan.name)
        model = ET.SubElement(diagram, "mxGraphModel")
        ET.SubElement(model, "root")
        return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)

    for tray in trays:
        tray_diff = diff.get(tray.pk, {"add": [], "remove": [], "unchanged": []})
        diagram = ET.SubElement(mxfile, "diagram", name=f"Tray: {tray}")

        model = ET.SubElement(diagram, "mxGraphModel")
        root = ET.SubElement(model, "root")

        # Required mxGraph root cells
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")

        # Get FrontPorts on this tray
        ports = FrontPort.objects.filter(device=plan.closure, module=tray).order_by("name")

        # Layout: ports as nodes, connections drawn between pairs
        y_offset = 40
        cell_id = 2
        port_cells = {}

        # Header
        header = ET.SubElement(
            root,
            "mxCell",
            id=str(cell_id),
            value=f"Tray: {tray}",
            style="text;fontStyle=1;fontSize=14",
            vertex="1",
            parent="1",
        )
        ET.SubElement(header, "mxGeometry", x="10", y="10", width="400", height="20", **{"as": "geometry"})
        cell_id += 1

        # Look up fiber strand colors via FiberStrand.front_port_a FK
        from netbox_fms.models import FiberStrand

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
            *[(p, "#000000", "") for p in tray_diff["unchanged"]],
            *[(p, "#00CC00", "dashed=1") for p in tray_diff["add"]],
            *[(p, "#CC0000", "dashed=1") for p in tray_diff["remove"]],
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

    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)
