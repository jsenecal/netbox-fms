"""Re-render FiberStrand names after a naming template change."""

from collections import Counter

from netbox_fms import naming
from netbox_fms.models import FiberStrand

from ._rerender_base import RerenderCommand


class Command(RerenderCommand):
    help = "Re-render FMS FiberStrand names from the current strand name template."

    def process_cable(self, fc, fct, dry_run):
        pending = []
        local_counter = Counter()
        for strand in fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position"):
            parent = strand.ribbon_id or strand.buffer_tube_id or 0
            local_counter[parent] += 1
            try:
                new_name = fct.resolve_strand_name(
                    **naming.strand_context(
                        cable=fc.cable,
                        cable_type=fct,
                        tube=strand.buffer_tube,
                        ribbon=strand.ribbon,
                        position=strand.position,
                        local=local_counter[parent],
                        strand_color_hex=strand.color,
                        color_scheme=fct.color_scheme,
                    )
                )
            except naming.NamingError as exc:
                self.stderr.write(f"{fc}: strand template failed: {exc}")
                return
            if self.stage_rendered(strand, "strand", name=new_name):
                pending.append(strand)

        self.write_updates(FiberStrand, pending, {"name"}, dry_run)
