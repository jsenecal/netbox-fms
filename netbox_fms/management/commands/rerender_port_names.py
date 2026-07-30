"""Re-render FrontPort and RearPort names and labels after a template change."""

from dcim.models import FrontPort, PortMapping, RearPort
from django.db import transaction

from netbox_fms import naming
from netbox_fms.services import _determine_cable_end, render_port_strings, render_rear_port_strings
from netbox_fms.signals import _tray_name_for, _tray_position_for

from ._rerender_base import RerenderCommand

TARGET_CHOICES = ("names", "labels")

# Which naming targets each --targets value covers, for the static
# strand_name pre-flight below.
_NAMING_TARGETS = {
    "names": (naming.FRONT_PORT_NAME, naming.REAR_PORT_NAME),
    "labels": (naming.FRONT_PORT_LABEL, naming.REAR_PORT_LABEL),
}


class Command(RerenderCommand):
    help = "Re-render FMS FrontPort and RearPort names and labels from the current templates."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--targets",
            default=",".join(TARGET_CHOICES),
            help=f"Comma-separated subset of: {', '.join(TARGET_CHOICES)}",
        )

    def prepare(self, options):
        self.targets = {t.strip() for t in options["targets"].split(",") if t.strip()}
        unknown = self.targets - set(TARGET_CHOICES)
        if unknown:
            self.stderr.write(f"Unknown target(s): {', '.join(sorted(unknown))}")
            return False
        return True

    def check_cable_type(self, fct):
        """Warn when a port template reads the strand name column this run does not write.

        ``{{ strand_name }}`` renders from ``FiberStrand.name`` as currently
        stored, so a port re-render run before ``rerender_strand_names``
        embeds the OLD strand names. The single command these two replaced
        ordered the two passes itself; split apart, the ordering is the
        operator's to get right, so say so. Detected statically, the same way
        ``naming.uses_tray`` detects the tray tokens. Warn and proceed: the
        render is not wrong, only potentially stale.
        """
        checked = tuple(t for value in sorted(self.targets) for t in _NAMING_TARGETS[value])
        if naming.uses_tokens(fct, checked, {naming.STRAND_NAME}):
            self.stderr.write(
                f"Warning: port templates for {fct} reference strand_name; "
                f"run rerender_strand_names first or the rendered port names will "
                f"embed stale strand names."
            )

    def _scoped(self, name, label):
        """Drop targets excluded by --targets to None ("leave that field alone")."""
        return (
            name if "names" in self.targets else None,
            label if "labels" in self.targets else None,
        )

    def process_cable(self, fc, fct, dry_run):
        proposed, tube_by_fp_id = self._front_ports(fc)
        if proposed is None:
            return
        rear = self._rear_ports(fc, tube_by_fp_id)
        if rear is None:
            return
        proposed.update(rear)

        if not self.check_collisions(proposed):
            return

        pending = {FrontPort: [], RearPort: []}
        fields = {FrontPort: set(), RearPort: set()}
        for port, (name, label) in proposed.items():
            model = type(port)
            changed = self.stage_rendered(port, model.__name__, name=name, label=label)
            if changed:
                fields[model] |= changed
                pending[model].append(port)

        if dry_run:
            return
        # Only the columns a render actually changed: a run with no label
        # template configured must not write the label column at all.
        with transaction.atomic():
            for model in (FrontPort, RearPort):
                self.write_updates(model, pending[model], fields[model], dry_run=False)

    def _front_ports(self, fc):
        """Render every FrontPort of the cable's strands.

        Returns ``({port: (name, label)}, {front_port_id: buffer_tube})``, or
        ``(None, None)`` if a template failed. The tube map is built here
        because the rear-port walk needs it and the strands are already in
        hand: a RearPort has no relation of its own to a BufferTube.
        """
        proposed = {}
        tube_by_fp_id = {}
        strands = fc.fiber_strands.select_related("buffer_tube", "ribbon", "front_port_a", "front_port_b")
        for strand in strands.all():
            for port in (strand.front_port_a, strand.front_port_b):
                if port is None:
                    continue
                try:
                    name, label = render_port_strings(
                        port,
                        strand,
                        strand.buffer_tube,
                        _tray_name_for(port),
                        _tray_position_for(port),
                    )
                except naming.NamingError as exc:
                    self.stderr.write(f"{fc}: front port template failed: {exc}")
                    return None, None
                proposed[port] = self._scoped(name, label)
                tube_by_fp_id[port.pk] = strand.buffer_tube
        return proposed, tube_by_fp_id

    def _rear_ports(self, fc, tube_by_fp_id):
        """Render every RearPort reachable from the cable's FrontPorts.

        Nothing in FMS relates a RearPort to a FiberCable, BufferTube or
        FiberStrand, so the only route is the ``dcim.PortMapping`` hop that
        ``_provision_device_ports`` creates and ``_rename_ports_for_cable``
        already walks. Every FrontPort mapped to one RearPort belongs to the
        same buffer tube by construction, so any of them supplies the tube.

        The tray tokens are resolved per rear port, matching
        ``_rename_ports_for_cable`` exactly. FMS never assigns
        ``RearPort.module``, but an operator can through the NetBox UI, and
        ``tray``/``tray_position`` are both in ``naming._REAR_TOKENS`` -- so
        rendering ``None`` here while the cable-save signal renders the real
        tray would make such a port's name flip-flop between the two paths.

        Returns ``{port: (name, label)}``, or ``None`` if a template failed.
        """
        if not tube_by_fp_id:
            return {}

        rear_ports = {}
        tube_by_rp_id = {}
        # rear_port__module__module_bay so _tray_name_for costs no extra query;
        # _tray_position_for short-circuits on the (normal) module_id=None case.
        pms = PortMapping.objects.filter(front_port_id__in=tube_by_fp_id).select_related(
            "rear_port__device", "rear_port__module__module_bay"
        )
        for pm in pms:
            rear_ports[pm.rear_port_id] = pm.rear_port
            if tube_by_rp_id.get(pm.rear_port_id) is None:
                tube_by_rp_id[pm.rear_port_id] = tube_by_fp_id.get(pm.front_port_id)

        proposed = {}
        end_by_device_id = {}
        for rp_id, rp in rear_ports.items():
            device = rp.device
            # _determine_cable_end runs queries; one cable rarely spans more
            # than two devices, so memoize per device exactly as
            # _rename_ports_for_cable does.
            if device.pk not in end_by_device_id:
                end_by_device_id[device.pk] = _determine_cable_end(fc.cable, device)
            try:
                name, label = render_rear_port_strings(
                    rp,
                    fc,
                    tube_by_rp_id.get(rp_id),
                    end_by_device_id[device.pk],
                    _tray_name_for(rp),
                    _tray_position_for(rp),
                )
            except naming.NamingError as exc:
                self.stderr.write(f"{fc}: rear port template failed: {exc}")
                return None
            proposed[rp] = self._scoped(name, label)
        return proposed
