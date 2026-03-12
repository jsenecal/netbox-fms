(function () {
    "use strict";

    var config = window.SPLICE_EDITOR_CONFIG;
    if (!config) return;

    // -----------------------------------------------------------------------
    // Layout constants
    // -----------------------------------------------------------------------
    var COLUMN_WIDTH   = 280;
    var STRAND_HEIGHT  = 20;
    var STRAND_DOT_R   = 5;
    var TUBE_ROW_H     = 18;
    var CABLE_ROW_H    = 22;
    var GROUP_PAD      = 6;
    var HEADER_HEIGHT  = 28;
    var TOP_PAD        = 10;
    var TUBE_INDENT    = 14;
    var TUBE_DOT_R     = 4;
    var MIN_HEIGHT     = 500;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    var cableGroups    = [];
    var leftNodes      = [];
    var rightNodes     = [];
    var spliceEntries  = [];
    var mode           = "single";
    var selected       = null;
    var leftOffset     = 0;
    var rightOffset    = 0;

    var containerEl = document.getElementById("splice-canvas-container");
    var statusBar   = document.getElementById("splice-status");

    // -----------------------------------------------------------------------
    // Toolbar
    // -----------------------------------------------------------------------
    document.querySelectorAll("#splice-toolbar [data-mode]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll("#splice-toolbar [data-mode]").forEach(function (b) {
                b.classList.remove("active");
            });
            btn.classList.add("active");
            mode = btn.dataset.mode;
            clearSelection();
            setStatus("Mode: " + mode);
        });
    });

    function setStatus(msg) { statusBar.textContent = msg; }

    function clearSelection() {
        selected = null;
        svg.selectAll(".strand-node").classed("selected", false);
    }

    // -----------------------------------------------------------------------
    // SVG setup
    // -----------------------------------------------------------------------
    var containerWidth = containerEl.clientWidth || 900;

    var svg = d3.select(containerEl)
        .append("svg")
        .attr("class", "splice-editor-svg")
        .attr("width", containerWidth);

    // Clip paths for columns
    var defs = svg.append("defs");
    defs.append("clipPath").attr("id", "clip-left")
        .append("rect").attr("x", 0).attr("y", HEADER_HEIGHT)
        .attr("width", COLUMN_WIDTH);
    defs.append("clipPath").attr("id", "clip-right")
        .append("rect").attr("y", HEADER_HEIGHT)
        .attr("width", COLUMN_WIDTH);

    // Column backgrounds
    var leftBg = svg.append("rect").attr("class", "column-bg")
        .attr("x", 0).attr("y", 0).attr("width", COLUMN_WIDTH);
    var rightBg = svg.append("rect").attr("class", "column-bg")
        .attr("y", 0).attr("width", COLUMN_WIDTH);

    // Column headers
    svg.append("text").attr("class", "column-header")
        .attr("x", COLUMN_WIDTH / 2).attr("y", 18)
        .text("LEFT SIDE");
    var rightHeader = svg.append("text").attr("class", "column-header")
        .attr("y", 18).text("RIGHT SIDE");

    // Render order: links behind, columns on top
    var linksGroup = svg.append("g").attr("class", "links-group");
    var leftGroup  = svg.append("g").attr("clip-path", "url(#clip-left)");
    var leftInner  = leftGroup.append("g");
    var rightGroup = svg.append("g");
    var rightInner = rightGroup.append("g");

    // D3 link generator
    var linkGen = d3.linkHorizontal()
        .x(function (d) { return d.x; })
        .y(function (d) { return d.y; });

    // -----------------------------------------------------------------------
    // Data loading
    // -----------------------------------------------------------------------
    async function loadData() {
        try {
            var resp = await fetch(config.apiBase);
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            cableGroups = await resp.json();
            processData();
            render();
            setStatus("Loaded " + cableGroups.length + " cable(s). Click strands to splice.");
        } catch (err) {
            setStatus("Error: " + err.message);
        }
    }

    function processData() {
        var mid = Math.ceil(cableGroups.length / 2);
        leftNodes  = layoutColumn(cableGroups.slice(0, mid));
        rightNodes = layoutColumn(cableGroups.slice(mid));
        collectSpliceEntries();
        leftOffset = 0;
        rightOffset = 0;
    }

    function collectSpliceEntries() {
        spliceEntries = [];
        var seen = {};
        cableGroups.forEach(function (cg) {
            var all = [];
            cg.tubes.forEach(function (t) { all = all.concat(t.strands); });
            all = all.concat(cg.loose_strands);
            all.forEach(function (s) {
                if (s.splice_entry_id && s.spliced_to && !seen[s.splice_entry_id]) {
                    seen[s.splice_entry_id] = true;
                    spliceEntries.push({
                        entryId:  s.splice_entry_id,
                        sourceId: s.id,
                        targetId: s.spliced_to
                    });
                }
            });
        });
    }

    // Build flat node list with y positions for a column
    function layoutColumn(cables) {
        var nodes = [];
        var y = TOP_PAD;

        cables.forEach(function (cg) {
            nodes.push({
                type: "cable", label: cg.cable_label,
                y: y, cableId: cg.fiber_cable_id,
                fiberType: cg.fiber_type,
                strandCount: cg.strand_count
            });
            y += CABLE_ROW_H;

            cg.tubes.forEach(function (tube) {
                var tubeNode = {
                    type: "tube", label: tube.name,
                    color: tube.color, stripeColor: tube.stripe_color,
                    strandCount: tube.strand_count,
                    y: y, tubeId: tube.id,
                    collapsed: false
                };
                nodes.push(tubeNode);
                y += TUBE_ROW_H;

                tube.strands.forEach(function (s) {
                    nodes.push({
                        type: "strand", id: s.id, label: s.name,
                        color: s.color,
                        tubeColor: s.tube_color,
                        tubeName: s.tube_name,
                        ribbonName: s.ribbon_name,
                        ribbonColor: s.ribbon_color,
                        y: y,
                        frontPortId: s.front_port_id,
                        spliceEntryId: s.splice_entry_id,
                        splicedTo: s.spliced_to,
                        tubeId: tube.id,
                        parentTubeNode: tubeNode
                    });
                    y += STRAND_HEIGHT;
                });
                y += GROUP_PAD;
            });

            cg.loose_strands.forEach(function (s) {
                nodes.push({
                    type: "strand", id: s.id, label: s.name,
                    color: s.color,
                    tubeColor: null, tubeName: null,
                    ribbonName: s.ribbon_name,
                    ribbonColor: s.ribbon_color,
                    y: y,
                    frontPortId: s.front_port_id,
                    spliceEntryId: s.splice_entry_id,
                    splicedTo: s.spliced_to,
                    tubeId: null,
                    parentTubeNode: null
                });
                y += STRAND_HEIGHT;
            });
            y += GROUP_PAD;
        });

        return nodes;
    }

    // Recalculate y-positions, assigning collapsed strands the tube's y
    function recalcPositions(nodes) {
        var collapsedTubes = {};
        var tubeYMap = {};

        // First pass: find collapsed tubes
        nodes.forEach(function (n) {
            if (n.type === "tube" && n.collapsed) collapsedTubes[n.tubeId] = true;
        });

        // Second pass: assign y positions
        var y = TOP_PAD;
        nodes.forEach(function (n) {
            if (n.type === "strand" && n.tubeId && collapsedTubes[n.tubeId]) {
                // Collapsed strand: pin to its parent tube's y
                n.y = tubeYMap[n.tubeId] || y;
                n.hidden = true;
                return;
            }
            n.hidden = false;
            n.y = y;
            if (n.type === "cable") {
                y += CABLE_ROW_H;
            } else if (n.type === "tube") {
                tubeYMap[n.tubeId] = y;
                y += TUBE_ROW_H;
            } else {
                y += STRAND_HEIGHT;
            }
        });
    }

    // -----------------------------------------------------------------------
    // Rendering
    // -----------------------------------------------------------------------
    function render() {
        var leftHeight  = columnHeight(leftNodes);
        var rightHeight = columnHeight(rightNodes);
        var svgHeight   = Math.max(leftHeight, rightHeight, MIN_HEIGHT) + HEADER_HEIGHT;
        var rightX      = containerWidth - COLUMN_WIDTH;

        svg.attr("height", svgHeight);

        // Update backgrounds
        leftBg.attr("height", svgHeight);
        rightBg.attr("x", rightX).attr("height", svgHeight);

        // Update header
        rightHeader.attr("x", rightX + COLUMN_WIDTH / 2);

        // Update clip rects
        defs.select("#clip-left rect").attr("height", svgHeight);
        defs.select("#clip-right rect").attr("x", rightX).attr("height", svgHeight);
        rightGroup.attr("clip-path", "url(#clip-right)");

        renderColumn(leftInner, leftNodes, "left", 0);
        renderColumn(rightInner, rightNodes, "right", rightX);
        renderLinks();
        setupDrag(svgHeight);
    }

    function columnHeight(nodes) {
        if (!nodes.length) return MIN_HEIGHT;
        var visible = nodes.filter(function (n) { return !n.hidden; });
        if (!visible.length) return MIN_HEIGHT;
        var last = visible[visible.length - 1];
        return last.y + STRAND_HEIGHT + TOP_PAD;
    }

    function renderColumn(group, nodes, side, xOffset) {
        group.selectAll("*").remove();
        var g = group.append("g")
            .attr("transform", "translate(0," + HEADER_HEIGHT + ")");

        nodes.forEach(function (node) {
            if (node.hidden) return;

            if (node.type === "cable") {
                renderCableNode(g, node, side, xOffset);
            } else if (node.type === "tube") {
                renderTubeNode(g, node, side, xOffset, nodes);
            } else if (node.type === "strand") {
                renderStrandNode(g, node, side, xOffset);
            }
        });
    }

    function renderCableNode(g, node, side, xOffset) {
        var cg = g.append("g").attr("class", "cable-group");
        var textX = xOffset + (side === "left" ? 8 : COLUMN_WIDTH - 8);
        var anchor = side === "left" ? "start" : "end";

        cg.append("text")
            .attr("class", "cable-label")
            .attr("x", textX)
            .attr("y", node.y + 4)
            .attr("text-anchor", anchor)
            .text(node.label);

        // Subtitle: fiber type + strand count
        if (node.fiberType || node.strandCount) {
            var sub = [];
            if (node.fiberType) sub.push(node.fiberType);
            if (node.strandCount) sub.push(node.strandCount + "F");
            cg.append("text")
                .attr("class", "cable-subtitle")
                .attr("x", textX)
                .attr("y", node.y + 14)
                .attr("text-anchor", anchor)
                .attr("font-size", "9px")
                .attr("fill", "#6c757d")
                .text(sub.join(" \u2022 "));
        }
    }

    function renderTubeNode(g, node, side, xOffset, allNodes) {
        var tg = g.append("g").attr("class", "tube-group").style("cursor", "pointer");
        var dotX = xOffset + (side === "left" ? TUBE_INDENT : COLUMN_WIDTH - TUBE_INDENT);
        var textX = xOffset + (side === "left" ? TUBE_INDENT + 10 : COLUMN_WIDTH - TUBE_INDENT - 10);
        var anchor = side === "left" ? "start" : "end";

        // Tube color dot
        tg.append("circle")
            .attr("class", "tube-dot")
            .attr("cx", dotX).attr("cy", node.y)
            .attr("r", TUBE_DOT_R)
            .attr("fill", "#" + (node.color || "ccc"));

        // Stripe indicator (small arc or second dot)
        if (node.stripeColor) {
            tg.append("circle")
                .attr("cx", dotX + (side === "left" ? -3 : 3))
                .attr("cy", node.y - 3)
                .attr("r", 2)
                .attr("fill", "#" + node.stripeColor)
                .attr("stroke", "#dee2e6")
                .attr("stroke-width", 0.5);
        }

        // Label with strand count and collapse indicator
        var icon = node.collapsed ? "\u25b6 " : "\u25bc ";
        var countStr = " (" + (node.strandCount || "?") + "F)";
        tg.append("text")
            .attr("class", "tube-label")
            .attr("x", textX)
            .attr("y", node.y + 3)
            .attr("text-anchor", anchor)
            .text(icon + node.label + countStr);

        tg.on("click", function () {
            node.collapsed = !node.collapsed;
            recalcPositions(allNodes);
            render();
        });
    }

    function renderStrandNode(g, node, side, xOffset) {
        var dotX = side === "left"
            ? xOffset + COLUMN_WIDTH - 14
            : xOffset + 14;
        var indent = node.tubeId ? TUBE_INDENT + 10 : 8;
        var textX = side === "left"
            ? xOffset + indent
            : xOffset + COLUMN_WIDTH - indent;
        var anchor = side === "left" ? "start" : "end";

        var sg = g.append("g")
            .attr("class", "strand-node")
            .classed("spliced", !!node.spliceEntryId)
            .datum(node);

        // Tube color accent bar (thin vertical line next to strand)
        if (node.tubeColor) {
            var barX = side === "left" ? xOffset + indent - 6 : xOffset + COLUMN_WIDTH - indent + 4;
            sg.append("rect")
                .attr("x", barX)
                .attr("y", node.y - STRAND_HEIGHT / 2 + 3)
                .attr("width", 3)
                .attr("height", STRAND_HEIGHT - 4)
                .attr("rx", 1)
                .attr("fill", "#" + node.tubeColor)
                .attr("opacity", 0.6);
        }

        // Strand fiber dot
        sg.append("circle")
            .attr("class", "strand-dot")
            .attr("cx", dotX).attr("cy", node.y)
            .attr("r", STRAND_DOT_R)
            .attr("fill", "#" + (node.color || "ccc"));

        // Strand name (F#)
        sg.append("text")
            .attr("class", "strand-name")
            .attr("x", textX)
            .attr("y", node.y + 3)
            .attr("text-anchor", anchor)
            .text(node.label);

        // Ribbon badge (if present)
        if (node.ribbonName) {
            var ribbonX = side === "left" ? dotX - 20 : dotX + 20;
            sg.append("text")
                .attr("x", ribbonX)
                .attr("y", node.y + 3)
                .attr("text-anchor", "middle")
                .attr("font-size", "8px")
                .attr("fill", "#" + (node.ribbonColor || "999"))
                .attr("font-weight", "600")
                .text("R");
        }

        // Hover title
        var title = node.label;
        if (node.tubeName) title += " | Tube: " + node.tubeName;
        if (node.ribbonName) title += " | Ribbon: " + node.ribbonName;
        if (node.frontPortId) title += " | Port: #" + node.frontPortId;
        sg.append("title").text(title);

        sg.on("click", function (event) {
            event.stopPropagation();
            handleStrandClick(node, side);
        });
    }

    // -----------------------------------------------------------------------
    // Links
    // -----------------------------------------------------------------------
    function renderLinks() {
        linksGroup.selectAll("*").remove();

        var rightX  = containerWidth - COLUMN_WIDTH;
        var nodeMap = {};

        // Build position map for all strands (including hidden/collapsed ones)
        leftNodes.forEach(function (n) {
            if (n.type === "strand") {
                nodeMap[n.id] = {
                    x: COLUMN_WIDTH - 14,
                    y: n.y + HEADER_HEIGHT + leftOffset,
                    hidden: n.hidden
                };
            }
        });
        rightNodes.forEach(function (n) {
            if (n.type === "strand") {
                nodeMap[n.id] = {
                    x: rightX + 14,
                    y: n.y + HEADER_HEIGHT + rightOffset,
                    hidden: n.hidden
                };
            }
        });

        spliceEntries.forEach(function (entry) {
            var a = nodeMap[entry.sourceId];
            var b = nodeMap[entry.targetId];
            if (!a || !b) return;

            var pathD;
            if (Math.abs(a.x - b.x) < 10) {
                // Same-side splice: draw a loop out to the center
                var loopX = a.x < containerWidth / 2
                    ? Math.min(a.x + 120, containerWidth / 2 - 20)
                    : Math.max(a.x - 120, containerWidth / 2 + 20);
                pathD = "M" + a.x + "," + a.y
                    + " C" + loopX + "," + a.y
                    + " " + loopX + "," + b.y
                    + " " + b.x + "," + b.y;
            } else {
                // Cross-side splice: standard horizontal link
                var source = a.x < b.x ? a : b;
                var target = a.x < b.x ? b : a;
                pathD = linkGen({ source: source, target: target });
            }

            var sameSide = Math.abs(a.x - b.x) < 10;
            var path = linksGroup.append("path")
                .attr("class", "splice-link")
                .classed("same-side", sameSide)
                .attr("d", pathD)
                .datum(entry);

            // Dim links to collapsed strands
            if (a.hidden || b.hidden) {
                path.attr("opacity", 0.2)
                    .attr("stroke-dasharray", "3,3");
            }

            path.on("click", function (event, d) {
                if (mode === "delete") {
                    deleteSplice([d.entryId]);
                }
            });
        });
    }

    // -----------------------------------------------------------------------
    // Column drag/scroll
    // -----------------------------------------------------------------------
    function setupDrag(svgHeight) {
        // Use wheel scroll on each column half for independent scrolling
        // Also support drag on the background rects
        var rightX = containerWidth - COLUMN_WIDTH;

        var leftDrag = d3.drag()
            .on("drag", function (event) {
                var maxScroll = Math.max(0, columnHeight(leftNodes) + HEADER_HEIGHT - svgHeight);
                leftOffset = Math.max(-maxScroll, Math.min(0, leftOffset + event.dy));
                leftInner.attr("transform", "translate(0," + leftOffset + ")");
                renderLinks();
            });

        var rightDrag = d3.drag()
            .on("drag", function (event) {
                var maxScroll = Math.max(0, columnHeight(rightNodes) + HEADER_HEIGHT - svgHeight);
                rightOffset = Math.max(-maxScroll, Math.min(0, rightOffset + event.dy));
                rightInner.attr("transform", "translate(0," + rightOffset + ")");
                renderLinks();
            });

        leftBg.call(leftDrag).style("cursor", "grab");
        rightBg.call(rightDrag).style("cursor", "grab");

        // Wheel scroll on SVG — detect which half the cursor is in
        svg.on("wheel", function (event) {
            event.preventDefault();
            var mouseX = d3.pointer(event, svg.node())[0];
            var delta = -event.deltaY;

            if (mouseX < containerWidth / 2) {
                var maxL = Math.max(0, columnHeight(leftNodes) + HEADER_HEIGHT - svgHeight);
                leftOffset = Math.max(-maxL, Math.min(0, leftOffset + delta));
                leftInner.attr("transform", "translate(0," + leftOffset + ")");
            } else {
                var maxR = Math.max(0, columnHeight(rightNodes) + HEADER_HEIGHT - svgHeight);
                rightOffset = Math.max(-maxR, Math.min(0, rightOffset + delta));
                rightInner.attr("transform", "translate(0," + rightOffset + ")");
            }
            renderLinks();
        });
    }

    // -----------------------------------------------------------------------
    // Strand click handling
    // -----------------------------------------------------------------------
    function handleStrandClick(node, side) {
        if (mode === "delete") {
            if (node.spliceEntryId) deleteSplice([node.spliceEntryId]);
            return;
        }

        if (mode === "single") {
            if (!selected) {
                selected = { id: node.id, side: side };
                svg.selectAll(".strand-node")
                    .classed("selected", function (d) { return d && d.id === node.id; });
                setStatus("Selected " + node.label + ". Click another strand to splice.");
            } else if (selected.id === node.id) {
                // Clicked same strand — deselect
                clearSelection();
                setStatus("Selection cleared.");
            } else {
                // Allow splicing any two strands (same side or opposite)
                createSplices([{ fiber_a: selected.id, fiber_b: node.id }]);
                clearSelection();
            }
            return;
        }

        if (mode === "sequential") {
            if (!selected) {
                selected = { id: node.id, side: side };
                svg.selectAll(".strand-node")
                    .classed("selected", function (d) { return d && d.id === node.id; });
                setStatus("Sequential start: " + node.label + ". Click another strand to bulk-splice downward.");
            } else if (selected.id === node.id) {
                clearSelection();
                setStatus("Selection cleared.");
            } else {
                var startList = visibleStrandsFrom(selected.side, selected.id);
                var endList   = visibleStrandsFrom(side, node.id);
                var count = Math.min(startList.length, endList.length);
                var pairs = [];
                for (var i = 0; i < count; i++) {
                    if (!startList[i].spliceEntryId && !endList[i].spliceEntryId) {
                        pairs.push({ fiber_a: startList[i].id, fiber_b: endList[i].id });
                    }
                }
                if (pairs.length) createSplices(pairs);
                clearSelection();
            }
        }
    }

    function visibleStrandsFrom(side, startId) {
        var list = (side === "left" ? leftNodes : rightNodes)
            .filter(function (n) { return n.type === "strand" && !n.hidden; });
        var idx = list.findIndex(function (n) { return n.id === startId; });
        return idx >= 0 ? list.slice(idx) : [];
    }

    // -----------------------------------------------------------------------
    // API
    // -----------------------------------------------------------------------
    async function createSplices(pairs) {
        try {
            var resp = await fetch(config.bulkSpliceUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": config.csrfToken },
                body: JSON.stringify(pairs)
            });
            if (!resp.ok) {
                var err = await resp.json();
                throw new Error(err.error || "HTTP " + resp.status);
            }
            var result = await resp.json();
            setStatus("Created " + result.created.length + " splice(s).");
            await loadData();
        } catch (e) {
            setStatus("Error: " + e.message);
        }
    }

    async function deleteSplice(ids) {
        try {
            var resp = await fetch(config.bulkSpliceUrl, {
                method: "DELETE",
                headers: { "Content-Type": "application/json", "X-CSRFToken": config.csrfToken },
                body: JSON.stringify({ entry_ids: ids })
            });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var result = await resp.json();
            setStatus("Deleted " + result.deleted + " splice(s).");
            await loadData();
        } catch (e) {
            setStatus("Error: " + e.message);
        }
    }

    // -----------------------------------------------------------------------
    // Resize
    // -----------------------------------------------------------------------
    var resizeTimer;
    window.addEventListener("resize", function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            containerWidth = containerEl.clientWidth || 900;
            svg.attr("width", containerWidth);
            render();
        }, 150);
    });

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    loadData();
})();
