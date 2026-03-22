from dcim.choices import CableLengthUnitChoices
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.fields import ColorField, CounterCacheField
from utilities.tracking import TrackingModelMixin

from .choices import (
    ArmorTypeChoices,
    CableElementTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberCircuitStatusChoices,
    FiberTypeChoices,
    FireRatingChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
    StorageMethodChoices,
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .constants import get_eia598_color

__all__ = (
    "FiberCableType",
    "BufferTubeTemplate",
    "RibbonTemplate",
    "CableElementTemplate",
    "FiberCable",
    "BufferTube",
    "Ribbon",
    "FiberStrand",
    "CableElement",
    "SpliceProject",
    "SplicePlan",
    "SplicePlanEntry",
    "ClosureCableEntry",
    "SlackLoop",
    "FiberCircuit",
    "FiberCircuitPath",
    "FiberCircuitNode",
    "WdmDeviceTypeProfile",
    "WdmChannelTemplate",
    "WdmNode",
    "WdmTrunkPort",
    "WavelengthChannel",
    "WavelengthService",
    "WavelengthServiceCircuit",
    "WavelengthServiceChannelAssignment",
    "WavelengthServiceNode",
)


# ---------------------------------------------------------------------------
# Type-level models (blueprints)
# ---------------------------------------------------------------------------


class FiberCableType(NetBoxModel):
    """
    A type/model of fiber cable, analogous to DeviceType.
    Defines the physical construction, sheathing, ratings, and inner structure
    of a cable via component templates (BufferTubeTemplate, CableElementTemplate).
    """

    manufacturer = models.ForeignKey(
        to="dcim.Manufacturer",
        on_delete=models.PROTECT,
        related_name="fiber_cable_types",
    )
    model = models.CharField(
        verbose_name=_("model"),
        max_length=100,
    )
    part_number = models.CharField(
        verbose_name=_("part number"),
        max_length=100,
        blank=True,
    )

    # Fiber properties
    construction = models.CharField(
        verbose_name=_("construction"),
        max_length=50,
        choices=ConstructionChoices,
    )
    fiber_type = models.CharField(
        verbose_name=_("fiber type"),
        max_length=50,
        choices=FiberTypeChoices,
    )
    strand_count = models.PositiveIntegerField(
        verbose_name=_("strand count"),
        help_text=_("Total number of fiber strands in the cable."),
    )

    # Sheath / jacket
    sheath_material = models.CharField(
        verbose_name=_("sheath material"),
        max_length=50,
        choices=SheathMaterialChoices,
        blank=True,
    )
    jacket_color = ColorField(
        verbose_name=_("jacket color"),
        blank=True,
    )

    # Armor
    is_armored = models.BooleanField(
        verbose_name=_("armored"),
        default=False,
    )
    armor_type = models.CharField(
        verbose_name=_("armor type"),
        max_length=50,
        choices=ArmorTypeChoices,
        blank=True,
    )

    # Deployment / environment
    deployment = models.CharField(
        verbose_name=_("deployment type"),
        max_length=50,
        choices=DeploymentChoices,
        blank=True,
    )
    fire_rating = models.CharField(
        verbose_name=_("fire rating"),
        max_length=50,
        choices=FireRatingChoices,
        blank=True,
    )

    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    buffer_tube_template_count = CounterCacheField(
        to_model="netbox_fms.BufferTubeTemplate",
        to_field="fiber_cable_type",
    )
    ribbon_template_count = CounterCacheField(
        to_model="netbox_fms.RibbonTemplate",
        to_field="fiber_cable_type",
    )
    cable_element_template_count = CounterCacheField(
        to_model="netbox_fms.CableElementTemplate",
        to_field="fiber_cable_type",
    )

    clone_fields = (
        "manufacturer",
        "construction",
        "fiber_type",
        "strand_count",
        "sheath_material",
        "jacket_color",
        "is_armored",
        "armor_type",
        "deployment",
        "fire_rating",
    )

    class Meta:
        ordering = ("manufacturer", "model")
        unique_together = ("manufacturer", "model")
        verbose_name = _("fiber cable type")
        verbose_name_plural = _("fiber cable types")

    def __str__(self):
        """Return manufacturer and model name."""
        return f"{self.manufacturer} {self.model}"

    def get_absolute_url(self):
        """Return the detail URL for this fiber cable type."""
        return reverse("plugins:netbox_fms:fibercabletype", args=[self.pk])

    def clean(self):
        """Validate armor consistency and strand count against templates."""
        super().clean()

        # Armor type required if armored
        if self.is_armored and not self.armor_type:
            raise ValidationError({"armor_type": _("Armor type is required when cable is armored.")})
        if not self.is_armored and self.armor_type:
            raise ValidationError({"armor_type": _("Armor type should be blank when cable is not armored.")})

        # Validate strand_count matches templates (only if templates exist)
        if self.pk:
            template_count = self.get_strand_count_from_templates()
            if template_count > 0 and template_count != self.strand_count:
                raise ValidationError(
                    {
                        "strand_count": _(
                            "strand_count ({declared}) does not match the total fibers from templates ({computed})."
                        ).format(declared=self.strand_count, computed=template_count)
                    }
                )

    def get_strand_count_from_templates(self):
        """Compute total fiber count from buffer tube templates."""
        return sum(btt.get_total_fiber_count() for btt in self.buffer_tube_templates.all())

    def get_cable_profile(self):
        """Derive the cable profile key from template topology.

        Checks both built-in NetBox profiles (CableProfileChoices) and custom
        fiber profiles registered via monkey-patch (FIBER_CABLE_PROFILES).
        """
        from dcim.choices import CableProfileChoices

        # Flatten all valid profile keys (built-in + monkey-patched custom)
        valid = set()
        for group in CableProfileChoices.CHOICES:
            for choice in group[1]:
                if isinstance(choice, (list, tuple)):
                    valid.add(choice[0])

        tubes = list(self.buffer_tube_templates.all())
        if not tubes:
            key = f"single-1c{self.strand_count}p"
            return key if key in valid else None

        fiber_counts = [t.get_total_fiber_count() for t in tubes]
        if len(set(fiber_counts)) != 1:
            return None

        key = f"trunk-{len(tubes)}c{fiber_counts[0]}p"
        return key if key in valid else None


class BufferTubeTemplate(TrackingModelMixin, NetBoxModel):
    """
    Defines a buffer tube within a FiberCableType.
    A tube contains either loose fibers (fiber_count set) or ribbons
    (fiber_count left blank, RibbonTemplates attached instead).
    """

    fiber_cable_type = models.ForeignKey(
        to="netbox_fms.FiberCableType",
        on_delete=models.CASCADE,
        related_name="buffer_tube_templates",
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    position = models.PositiveIntegerField(
        verbose_name=_("position"),
    )
    color = ColorField(
        verbose_name=_("color"),
        blank=True,
    )
    stripe_color = ColorField(
        verbose_name=_("stripe color"),
        blank=True,
        help_text=_("Stripe/dash color for identification beyond 12 tubes (EIA/TIA-598)."),
    )
    fiber_count = models.PositiveIntegerField(
        verbose_name=_("fiber count"),
        help_text=_("Number of loose fibers in this tube. Leave blank if tube contains ribbons."),
        blank=True,
        null=True,
    )
    description = models.CharField(
        verbose_name=_("description"),
        max_length=200,
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable_type", "position")
        unique_together = ("fiber_cable_type", "name")
        verbose_name = _("buffer tube template")
        verbose_name_plural = _("buffer tube templates")

    def __str__(self):
        """Return cable type and tube name."""
        return f"{self.fiber_cable_type} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this buffer tube template."""
        return reverse("plugins:netbox_fms:buffertubetemplate", args=[self.pk])

    def clean(self):
        """Validate that fiber_count and ribbon templates are mutually exclusive."""
        super().clean()
        if self.pk and self.fiber_count and self.ribbon_templates.exists():
            raise ValidationError(
                {
                    "fiber_count": _(
                        "A tube cannot have both fiber_count and ribbon templates. "
                        "Set fiber_count to blank if this tube uses ribbons."
                    )
                }
            )

    def get_total_fiber_count(self):
        """Total fibers: either fiber_count (loose) or sum of ribbon fiber counts."""
        if self.fiber_count:
            return self.fiber_count
        total = self.ribbon_templates.aggregate(total=models.Sum("fiber_count"))["total"]
        return total or 0

    def instantiate(self, fiber_cable):
        """Create a BufferTube instance for the given FiberCable."""
        return BufferTube(
            fiber_cable=fiber_cable,
            name=self.name,
            position=self.position,
            color=self.color,
            stripe_color=self.stripe_color,
        )


class RibbonTemplate(TrackingModelMixin, NetBoxModel):
    """
    Defines a fiber ribbon within a FiberCableType.
    A ribbon may live inside a BufferTubeTemplate (ribbon-in-tube construction)
    or directly on the FiberCableType (central-core ribbon construction).
    """

    fiber_cable_type = models.ForeignKey(
        to="netbox_fms.FiberCableType",
        on_delete=models.CASCADE,
        related_name="ribbon_templates",
    )
    buffer_tube_template = models.ForeignKey(
        to="netbox_fms.BufferTubeTemplate",
        on_delete=models.CASCADE,
        related_name="ribbon_templates",
        blank=True,
        null=True,
        help_text=_("Parent tube for ribbon-in-tube construction. Leave blank for central-core ribbon."),
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    position = models.PositiveIntegerField(
        verbose_name=_("position"),
    )
    color = ColorField(
        verbose_name=_("color"),
        blank=True,
    )
    stripe_color = ColorField(
        verbose_name=_("stripe color"),
        blank=True,
        help_text=_("Stripe/dash color for identification beyond 12 ribbons (EIA/TIA-598)."),
    )
    fiber_count = models.PositiveIntegerField(
        verbose_name=_("fiber count"),
        help_text=_("Number of fibers in this ribbon (typically 12 or 24)."),
    )
    description = models.CharField(
        verbose_name=_("description"),
        max_length=200,
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable_type", "buffer_tube_template", "position")
        constraints = [
            models.UniqueConstraint(
                fields=["fiber_cable_type", "buffer_tube_template", "name"],
                name="unique_ribbon_template_with_tube",
                condition=models.Q(buffer_tube_template__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["fiber_cable_type", "name"],
                name="unique_ribbon_template_without_tube",
                condition=models.Q(buffer_tube_template__isnull=True),
            ),
        ]
        verbose_name = _("ribbon template")
        verbose_name_plural = _("ribbon templates")

    def __str__(self):
        """Return parent (tube or cable type) and ribbon name."""
        parent = self.buffer_tube_template or self.fiber_cable_type
        return f"{parent} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this ribbon template."""
        return reverse("plugins:netbox_fms:ribbontemplate", args=[self.pk])

    def instantiate(self, fiber_cable, buffer_tube=None):
        """Create a Ribbon instance for the given FiberCable."""
        return Ribbon(
            fiber_cable=fiber_cable,
            buffer_tube=buffer_tube,
            name=self.name,
            position=self.position,
            color=self.color,
            stripe_color=self.stripe_color,
        )


class CableElementTemplate(TrackingModelMixin, NetBoxModel):
    """
    Defines a non-fiber component within a FiberCableType
    (strength members, power conductors, tracer wire, etc.).
    """

    fiber_cable_type = models.ForeignKey(
        to="netbox_fms.FiberCableType",
        on_delete=models.CASCADE,
        related_name="cable_element_templates",
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    element_type = models.CharField(
        verbose_name=_("element type"),
        max_length=50,
        choices=CableElementTypeChoices,
    )
    description = models.CharField(
        verbose_name=_("description"),
        max_length=200,
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable_type", "name")
        unique_together = ("fiber_cable_type", "name")
        verbose_name = _("cable element template")
        verbose_name_plural = _("cable element templates")

    def __str__(self):
        """Return cable type and element name."""
        return f"{self.fiber_cable_type} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this cable element template."""
        return reverse("plugins:netbox_fms:cableelementtemplate", args=[self.pk])

    def instantiate(self, fiber_cable):
        """Create a CableElement instance for the given FiberCable."""
        return CableElement(
            fiber_cable=fiber_cable,
            name=self.name,
            element_type=self.element_type,
        )


# ---------------------------------------------------------------------------
# Instance-level models
# ---------------------------------------------------------------------------


class FiberCable(NetBoxModel):
    """
    An instance of a FiberCableType, linked 1:1 to a NetBox Cable.
    Analogous to Device (instance of DeviceType).
    On creation, auto-instantiates BufferTubes, FiberStrands, and CableElements
    from the FiberCableType's templates.
    """

    cable = models.OneToOneField(
        to="dcim.Cable",
        on_delete=models.CASCADE,
        related_name="fiber_attributes",
    )
    fiber_cable_type = models.ForeignKey(
        to="netbox_fms.FiberCableType",
        on_delete=models.PROTECT,
        related_name="instances",
    )
    serial_number = models.CharField(
        verbose_name=_("serial number"),
        max_length=100,
        blank=True,
    )
    install_date = models.DateField(
        verbose_name=_("install date"),
        blank=True,
        null=True,
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("cable",)
        verbose_name = _("fiber cable")
        verbose_name_plural = _("fiber cables")

    def __str__(self):
        """Return cable and fiber cable type."""
        return f"{self.cable} ({self.fiber_cable_type})"

    def get_absolute_url(self):
        """Return the detail URL for this fiber cable."""
        return reverse("plugins:netbox_fms:fibercable", args=[self.pk])

    def save(self, *args, **kwargs):
        """Save and auto-instantiate components on first creation."""
        is_new = self.pk is None
        if is_new:
            with transaction.atomic():
                super().save(*args, **kwargs)
                self._instantiate_components()
        else:
            super().save(*args, **kwargs)

    def _instantiate_components(self):
        """
        Create tubes, ribbons, fibers, and cable elements from the type's templates.

        Handles four construction cases:
        1. Loose tube: tubes with fiber_count → fibers directly in tube
        2. Ribbon-in-tube: tubes with RibbonTemplates → ribbons inside tubes → fibers in ribbons
        3. Central-core ribbon: RibbonTemplates on type (no tube) → ribbons → fibers in ribbons
        4. Tight buffer / no tubes: fibers directly on cable
        """
        fct = self.fiber_cable_type
        strand_position = 1

        tube_templates = fct.buffer_tube_templates.all().order_by("position")
        # Central-core ribbons: ribbon templates not assigned to any tube
        central_ribbon_templates = fct.ribbon_templates.filter(
            buffer_tube_template__isnull=True,
        ).order_by("position")

        # Process buffer tubes
        for tt in tube_templates:
            tube = tt.instantiate(fiber_cable=self)
            tube.save()

            ribbon_templates = tt.ribbon_templates.all().order_by("position")
            if ribbon_templates.exists():
                # Ribbon-in-tube: create ribbons and fibers within each ribbon
                for rt in ribbon_templates:
                    ribbon = rt.instantiate(fiber_cable=self, buffer_tube=tube)
                    ribbon.save()
                    strand_position = self._create_fibers_in_ribbon(
                        ribbon,
                        tube,
                        rt.fiber_count,
                        strand_position,
                    )
            elif tt.fiber_count:
                # Loose tube: create fibers directly in tube
                fibers = []
                for i in range(1, tt.fiber_count + 1):
                    hex_color, _ = get_eia598_color(i)
                    fibers.append(
                        FiberStrand(
                            fiber_cable=self,
                            buffer_tube=tube,
                            name=f"{tube.name}-F{i}",
                            position=strand_position,
                            color=hex_color,
                        )
                    )
                    strand_position += 1
                FiberStrand.objects.bulk_create(fibers)

        # Central-core ribbons (no tube)
        if central_ribbon_templates.exists():
            for rt in central_ribbon_templates:
                ribbon = rt.instantiate(fiber_cable=self)
                ribbon.save()
                strand_position = self._create_fibers_in_ribbon(
                    ribbon,
                    None,
                    rt.fiber_count,
                    strand_position,
                )
        elif not tube_templates.exists():
            # Tight buffer / simple cable: create fibers directly on cable
            fibers = []
            for i in range(1, fct.strand_count + 1):
                hex_color, _ = get_eia598_color(i)
                fibers.append(
                    FiberStrand(
                        fiber_cable=self,
                        name=f"F{i}",
                        position=i,
                        color=hex_color,
                    )
                )
            FiberStrand.objects.bulk_create(fibers)

        # Instantiate cable elements
        elements = [et.instantiate(fiber_cable=self) for et in fct.cable_element_templates.all()]
        if elements:
            CableElement.objects.bulk_create(elements)

    def _create_fibers_in_ribbon(self, ribbon, buffer_tube, fiber_count, start_position):
        """Create fiber strands within a ribbon. Returns next strand position."""
        fibers = []
        for i in range(1, fiber_count + 1):
            hex_color, _ = get_eia598_color(i)
            fibers.append(
                FiberStrand(
                    fiber_cable=self,
                    buffer_tube=buffer_tube,
                    ribbon=ribbon,
                    name=f"{ribbon.name}-F{i}",
                    position=start_position,
                    color=hex_color,
                )
            )
            start_position += 1
        FiberStrand.objects.bulk_create(fibers)
        return start_position


class BufferTube(NetBoxModel):
    """
    A buffer tube instance within a FiberCable.
    Contains FiberStrand children.
    """

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="buffer_tubes",
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    position = models.PositiveIntegerField(
        verbose_name=_("position"),
    )
    color = ColorField(
        verbose_name=_("color"),
        blank=True,
    )
    stripe_color = ColorField(
        verbose_name=_("stripe color"),
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable", "position")
        unique_together = ("fiber_cable", "name")
        verbose_name = _("buffer tube")
        verbose_name_plural = _("buffer tubes")

    def __str__(self):
        """Return cable and tube name."""
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this buffer tube."""
        return reverse("plugins:netbox_fms:buffertube", args=[self.pk])


class Ribbon(NetBoxModel):
    """
    A fiber ribbon instance within a FiberCable, optionally inside a BufferTube.
    Contains FiberStrand children.
    """

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="ribbons",
    )
    buffer_tube = models.ForeignKey(
        to="netbox_fms.BufferTube",
        on_delete=models.CASCADE,
        related_name="ribbons",
        blank=True,
        null=True,
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    position = models.PositiveIntegerField(
        verbose_name=_("position"),
    )
    color = ColorField(
        verbose_name=_("color"),
        blank=True,
    )
    stripe_color = ColorField(
        verbose_name=_("stripe color"),
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable", "position")
        unique_together = ("fiber_cable", "name")
        verbose_name = _("ribbon")
        verbose_name_plural = _("ribbons")

    def __str__(self):
        """Return cable and ribbon name."""
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this ribbon."""
        return reverse("plugins:netbox_fms:ribbon", args=[self.pk])


class FiberStrand(NetBoxModel):
    """
    An individual fiber strand within a FiberCable, optionally inside a BufferTube
    and/or a Ribbon.
    """

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="fiber_strands",
    )
    buffer_tube = models.ForeignKey(
        to="netbox_fms.BufferTube",
        on_delete=models.CASCADE,
        related_name="fiber_strands",
        blank=True,
        null=True,
    )
    ribbon = models.ForeignKey(
        to="netbox_fms.Ribbon",
        on_delete=models.CASCADE,
        related_name="fiber_strands",
        blank=True,
        null=True,
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    position = models.PositiveIntegerField(
        verbose_name=_("position"),
        help_text=_("Overall strand position within the cable (1-indexed)."),
    )
    color = ColorField(
        verbose_name=_("color"),
        blank=True,
    )
    front_port_a = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands_a",
        blank=True,
        null=True,
        verbose_name=_("front port (A-side)"),
        help_text=_("The dcim FrontPort on the cable's A-side termination."),
    )
    front_port_b = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands_b",
        blank=True,
        null=True,
        verbose_name=_("front port (B-side)"),
        help_text=_("The dcim FrontPort on the cable's B-side termination."),
    )

    class Meta:
        ordering = ("fiber_cable", "position")
        unique_together = ("fiber_cable", "position")
        verbose_name = _("fiber strand")
        verbose_name_plural = _("fiber strands")

    def __str__(self):
        """Return cable and strand name."""
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this fiber strand."""
        return reverse("plugins:netbox_fms:fiberstrand", args=[self.pk])


class CableElement(NetBoxModel):
    """
    A non-fiber component within a FiberCable
    (strength member, power conductor, tracer wire, etc.).
    """

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="cable_elements",
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=64,
    )
    element_type = models.CharField(
        verbose_name=_("element type"),
        max_length=50,
        choices=CableElementTypeChoices,
    )

    class Meta:
        ordering = ("fiber_cable", "name")
        unique_together = ("fiber_cable", "name")
        verbose_name = _("cable element")
        verbose_name_plural = _("cable elements")

    def __str__(self):
        """Return cable and element name."""
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
        """Return the detail URL for this cable element."""
        return reverse("plugins:netbox_fms:cableelement", args=[self.pk])


# ---------------------------------------------------------------------------
# Splice planning
# ---------------------------------------------------------------------------


class SpliceProject(NetBoxModel):
    """Groups multiple closure-level splice plans into a route/job scope."""

    name = models.CharField(
        verbose_name=_("name"),
        max_length=100,
    )
    description = models.TextField(
        verbose_name=_("description"),
        blank=True,
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("splice project")
        verbose_name_plural = _("splice projects")

    def __str__(self):
        """Return the project name."""
        return self.name

    def get_absolute_url(self):
        """Return the detail URL for this splice project."""
        return reverse("plugins:netbox_fms:spliceproject", args=[self.pk])


class SplicePlan(NetBoxModel):
    """
    A splice plan represents the desired state of all splice connections
    within a closure (Device). One plan per closure.
    """

    closure = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="splice_plan",
        verbose_name=_("closure"),
    )
    project = models.ForeignKey(
        to="netbox_fms.SpliceProject",
        on_delete=models.SET_NULL,
        related_name="plans",
        verbose_name=_("project"),
        blank=True,
        null=True,
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=100,
    )
    description = models.TextField(
        verbose_name=_("description"),
        blank=True,
    )
    status = models.CharField(
        verbose_name=_("status"),
        max_length=50,
        choices=SplicePlanStatusChoices,
        default=SplicePlanStatusChoices.DRAFT,
    )
    cached_diff = models.JSONField(
        verbose_name=_("cached diff"),
        blank=True,
        null=True,
    )
    diff_stale = models.BooleanField(
        verbose_name=_("diff stale"),
        default=True,
    )

    class Meta:
        ordering = ("closure", "name")
        verbose_name = _("splice plan")
        verbose_name_plural = _("splice plans")

    def __str__(self):
        """Return the plan name."""
        return self.name

    def get_absolute_url(self):
        """Return the detail URL for this splice plan."""
        return reverse("plugins:netbox_fms:spliceplan", args=[self.pk])


class SplicePlanEntry(NetBoxModel):
    """
    A single desired FrontPort↔FrontPort connection within a splice plan.
    Each entry represents one splice or inter-platter route.
    """

    plan = models.ForeignKey(
        to="netbox_fms.SplicePlan",
        on_delete=models.CASCADE,
        related_name="entries",
    )
    tray = models.ForeignKey(
        to="dcim.Module",
        on_delete=models.CASCADE,
        related_name="splice_plan_entries",
        verbose_name=_("tray"),
        help_text=_("Tray owning fiber_a (canonical tray for this entry)."),
    )
    fiber_a = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.CASCADE,
        related_name="splice_entries_a",
        verbose_name=_("fiber A"),
    )
    fiber_b = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.CASCADE,
        related_name="splice_entries_b",
        verbose_name=_("fiber B"),
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )
    is_express = models.BooleanField(
        verbose_name=_("express"),
        default=False,
        help_text=_("Fiber passes through closure without being physically spliced."),
    )

    class Meta:
        ordering = ("plan", "pk")
        unique_together = (
            ("plan", "fiber_a"),
            ("plan", "fiber_b"),
        )
        verbose_name = _("splice plan entry")
        verbose_name_plural = _("splice plan entries")

    def __str__(self):
        """Return fiber A to fiber B representation."""
        return f"{self.fiber_a} → {self.fiber_b}"

    def get_absolute_url(self):
        """Return the detail URL for this splice plan entry."""
        return reverse("plugins:netbox_fms:spliceplanentry", args=[self.pk])

    @property
    def is_inter_platter(self):
        """True if fiber_a and fiber_b are on different tray modules."""
        return self.fiber_a.module_id != self.fiber_b.module_id

    def clean(self):
        """Validate both FrontPorts belong to the closure and tray matches fiber_a."""
        super().clean()
        # Validate both FrontPorts belong to the plan's closure Device
        if self.fiber_a.device_id != self.plan.closure_id:
            raise ValidationError({"fiber_a": _("FrontPort must belong to the plan's closure device.")})
        if self.fiber_b.device_id != self.plan.closure_id:
            raise ValidationError({"fiber_b": _("FrontPort must belong to the plan's closure device.")})
        # Validate tray matches fiber_a's module
        if self.fiber_a.module_id != self.tray_id:
            raise ValidationError({"tray": _("Tray must match fiber_a's parent module.")})


class ClosureCableEntry(NetBoxModel):
    """Tracks which port/gland on a closure each cable enters through."""

    closure = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="cable_entries",
        verbose_name=_("closure"),
    )
    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="closure_entries",
        verbose_name=_("fiber cable"),
    )
    entrance_label = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("entrance label"),
        help_text=_("Free-text gland/entrance name"),
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("closure", "entrance_label")
        unique_together = (("closure", "fiber_cable"),)
        verbose_name = _("closure cable entry")
        verbose_name_plural = _("closure cable entries")

    def __str__(self):
        """Return closure, entrance label, and fiber cable."""
        label = self.entrance_label or "\u2014"
        return f"{self.closure} \u2192 {label} ({self.fiber_cable})"

    def get_absolute_url(self):
        """Return the detail URL for this closure cable entry."""
        return reverse("plugins:netbox_fms:closurecableentry", args=[self.pk])


# ---------------------------------------------------------------------------
# Slack Loops
# ---------------------------------------------------------------------------


class SlackLoop(NetBoxModel):
    """A coil of spare fiber cable left at a specific location along a route."""

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="slack_loops",
        verbose_name=_("fiber cable"),
    )
    site = models.ForeignKey(
        to="dcim.Site",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("site"),
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("location"),
        blank=True,
        null=True,
    )
    start_mark = models.DecimalField(
        verbose_name=_("start mark"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Sheath distance mark where the loop begins."),
    )
    end_mark = models.DecimalField(
        verbose_name=_("end mark"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Sheath distance mark where the loop ends."),
    )
    length_unit = models.CharField(
        verbose_name=_("length unit"),
        max_length=10,
        choices=CableLengthUnitChoices,
    )
    storage_method = models.CharField(
        verbose_name=_("storage method"),
        max_length=50,
        choices=StorageMethodChoices,
        blank=True,
    )
    notes = models.TextField(verbose_name=_("notes"), blank=True)

    class Meta:
        ordering = ("fiber_cable", "start_mark")
        unique_together = ("fiber_cable", "start_mark", "end_mark")
        verbose_name = _("slack loop")
        verbose_name_plural = _("slack loops")

    def __str__(self):
        """Return cable, start/end marks, and length unit."""
        return f"{self.fiber_cable} @ {self.start_mark}\u2013{self.end_mark} {self.length_unit}"

    def get_absolute_url(self):
        """Return the detail URL for this slack loop."""
        return reverse("plugins:netbox_fms:slackloop", args=[self.pk])

    @property
    def loop_length(self):
        """Return the length of the slack loop (end_mark minus start_mark)."""
        return self.end_mark - self.start_mark

    def clean(self):
        """Validate that start and end marks are non-negative."""
        super().clean()
        if self.start_mark is not None and self.start_mark < 0:
            raise ValidationError({"start_mark": _("Start mark must be non-negative.")})
        if self.end_mark is not None and self.end_mark < 0:
            raise ValidationError({"end_mark": _("End mark must be non-negative.")})

    def save(self, *args, **kwargs):
        """Swap start/end marks if inverted, then save."""
        if self.start_mark is not None and self.end_mark is not None and self.end_mark < self.start_mark:
            self.start_mark, self.end_mark = self.end_mark, self.start_mark
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fiber Circuits
# ---------------------------------------------------------------------------


class FiberCircuit(NetBoxModel):
    """End-to-end logical fiber service with one or more parallel strand paths."""

    name = models.CharField(max_length=200, verbose_name=_("name"))
    cid = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("circuit ID"),
        help_text=_("External circuit identifier"),
    )
    status = models.CharField(
        max_length=50,
        choices=FiberCircuitStatusChoices,
        default=FiberCircuitStatusChoices.PLANNED,
        verbose_name=_("status"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    strand_count = models.PositiveIntegerField(verbose_name=_("strand count"))
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="fiber_circuits",
        verbose_name=_("tenant"),
    )
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    class Meta:
        ordering = ("name",)
        verbose_name = _("fiber circuit")
        verbose_name_plural = _("fiber circuits")

    def __str__(self):
        """Return the circuit name."""
        return self.name

    def get_absolute_url(self):
        """Return the detail URL for this fiber circuit."""
        return reverse("plugins:netbox_fms:fibercircuit", args=[self.pk])

    def save(self, *args, **kwargs):
        """Save and rebuild or delete nodes on status transitions."""
        is_new = self.pk is None
        old_status = None
        if not is_new:
            old_status = FiberCircuit.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        super().save(*args, **kwargs)
        if not is_new and old_status != self.status:
            if self.status == FiberCircuitStatusChoices.DECOMMISSIONED:
                FiberCircuitNode.objects.filter(path__circuit=self).delete()
            elif old_status == FiberCircuitStatusChoices.DECOMMISSIONED:
                for path in self.paths.all():
                    path.rebuild_nodes()

    @classmethod
    def find_paths(cls, origin_device, destination_device, strand_count=1, priorities=None, max_results=20):
        """Find available fiber paths between two devices.

        Delegates to the provisioning engine. See
        ``netbox_fms.provisioning.find_fiber_paths`` for full documentation.
        """
        from .provisioning import find_fiber_paths

        return find_fiber_paths(
            origin_device,
            destination_device,
            strand_count=strand_count,
            priorities=priorities,
            max_results=max_results,
        )

    @classmethod
    def create_from_proposal(cls, proposal, name_template="Circuit-{n}"):
        """Create a FiberCircuit from a selected proposal.

        Delegates to the provisioning engine. See
        ``netbox_fms.provisioning.create_circuit_from_proposal`` for full documentation.
        """
        from .provisioning import create_circuit_from_proposal

        return create_circuit_from_proposal(proposal, name_template=name_template)


class FiberCircuitPath(NetBoxModel):
    """One strand's end-to-end journey through cables and splices."""

    circuit = models.ForeignKey(
        to="netbox_fms.FiberCircuit",
        on_delete=models.CASCADE,
        related_name="paths",
        verbose_name=_("circuit"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))
    origin = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.PROTECT,
        related_name="fiber_circuit_path_origins",
        verbose_name=_("origin"),
    )
    destination = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_circuit_path_destinations",
        blank=True,
        null=True,
        verbose_name=_("destination"),
    )
    path = models.JSONField(default=list, verbose_name=_("path"))
    is_complete = models.BooleanField(default=False, verbose_name=_("complete"))
    calculated_loss_db = models.DecimalField(
        verbose_name=_("calculated loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    actual_loss_db = models.DecimalField(
        verbose_name=_("actual loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    wavelength_nm = models.PositiveIntegerField(
        verbose_name=_("wavelength (nm)"),
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("circuit", "position")
        unique_together = (("circuit", "position"),)
        verbose_name = _("fiber circuit path")
        verbose_name_plural = _("fiber circuit paths")

    def __str__(self):
        """Return circuit, position, origin, and destination."""
        dest = self.destination or "incomplete"
        return f"{self.circuit} path {self.position}: {self.origin} → {dest}"

    def get_absolute_url(self):
        """Return the detail URL for this fiber circuit path."""
        return reverse("plugins:netbox_fms:fibercircuitpath", args=[self.pk])

    def clean(self):
        """Validate wavelength is set when loss values exist and path count does not exceed strand count."""
        super().clean()
        if (self.calculated_loss_db is not None or self.actual_loss_db is not None) and self.wavelength_nm is None:
            raise ValidationError({"wavelength_nm": _("Wavelength is required when loss values are set.")})
        if self.circuit_id:
            existing = self.circuit.paths.exclude(pk=self.pk).count()
            if existing >= self.circuit.strand_count:
                raise ValidationError(
                    _("Cannot add more paths than the circuit's strand count (%(count)s)."),
                    params={"count": self.circuit.strand_count},
                )

    @classmethod
    def from_origin(cls, front_port):
        """Trace a fiber path from a FrontPort and return an unsaved FiberCircuitPath."""
        from .trace import trace_fiber_path

        result = trace_fiber_path(front_port)
        return cls(
            origin=result["origin"],
            destination=result["destination"],
            path=result["path"],
            is_complete=result["is_complete"],
        )

    def retrace(self):
        """Re-trace from origin, update path JSON, and atomically rebuild nodes."""
        from .trace import trace_fiber_path

        result = trace_fiber_path(self.origin)
        self.destination = result["destination"]
        self.path = result["path"]
        self.is_complete = result["is_complete"]
        self.save()
        if self.circuit.status != FiberCircuitStatusChoices.DECOMMISSIONED:
            self.rebuild_nodes()
        else:
            self.nodes.all().delete()

    def rebuild_nodes(self):
        """Walk self.path JSON and create FiberCircuitNode rows."""
        self.nodes.all().delete()
        position = 1
        for entry in self.path:
            node_type = entry["type"]
            obj_id = entry["id"]
            kwargs = {"path": self, "position": position}
            if node_type == "cable":
                kwargs["cable_id"] = obj_id
            elif node_type == "front_port":
                kwargs["front_port_id"] = obj_id
            elif node_type == "rear_port":
                kwargs["rear_port_id"] = obj_id
            elif node_type == "splice_entry":
                kwargs["splice_entry_id"] = obj_id
            FiberCircuitNode.objects.create(**kwargs)
            position += 1
        self._create_strand_nodes(position)

    def _create_strand_nodes(self, start_position):
        """Create FiberCircuitNode entries for FiberStrands derived from path FrontPorts."""
        fp_ids = [e["id"] for e in self.path if e["type"] == "front_port"]
        strands = FiberStrand.objects.filter(
            models.Q(front_port_a_id__in=fp_ids) | models.Q(front_port_b_id__in=fp_ids)
        ).distinct()
        pos = start_position
        for strand in strands:
            FiberCircuitNode.objects.create(path=self, position=pos, fiber_strand=strand)
            pos += 1


class FiberCircuitNode(models.Model):
    """Relational index of objects in a fiber circuit path for PROTECT-based deletion prevention."""

    path = models.ForeignKey(
        to="netbox_fms.FiberCircuitPath",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("path"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))
    cable = models.ForeignKey(
        to="dcim.Cable",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("cable"),
    )
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("front port"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("rear port"),
    )
    fiber_strand = models.ForeignKey(
        to="netbox_fms.FiberStrand",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("fiber strand"),
    )
    splice_entry = models.ForeignKey(
        to="netbox_fms.SplicePlanEntry",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("splice entry"),
    )

    class Meta:
        ordering = ("path", "position")
        unique_together = (("path", "position"),)
        verbose_name = _("fiber circuit node")
        verbose_name_plural = _("fiber circuit nodes")
        constraints = [
            models.CheckConstraint(
                name="fibercircuitnode_exactly_one_ref",
                condition=(
                    models.Q(
                        cable__isnull=False,
                        front_port__isnull=True,
                        rear_port__isnull=True,
                        fiber_strand__isnull=True,
                        splice_entry__isnull=True,
                    )
                    | models.Q(
                        cable__isnull=True,
                        front_port__isnull=False,
                        rear_port__isnull=True,
                        fiber_strand__isnull=True,
                        splice_entry__isnull=True,
                    )
                    | models.Q(
                        cable__isnull=True,
                        front_port__isnull=True,
                        rear_port__isnull=False,
                        fiber_strand__isnull=True,
                        splice_entry__isnull=True,
                    )
                    | models.Q(
                        cable__isnull=True,
                        front_port__isnull=True,
                        rear_port__isnull=True,
                        fiber_strand__isnull=False,
                        splice_entry__isnull=True,
                    )
                    | models.Q(
                        cable__isnull=True,
                        front_port__isnull=True,
                        rear_port__isnull=True,
                        fiber_strand__isnull=True,
                        splice_entry__isnull=False,
                    )
                ),
            ),
        ]

    def __str__(self):
        """Return the populated reference field and its value."""
        for field in ("cable", "front_port", "rear_port", "fiber_strand", "splice_entry"):
            obj = getattr(self, field)
            if obj is not None:
                return f"{field}: {obj}"
        return f"node #{self.position}"


# ---------------------------------------------------------------------------
# WDM (Wavelength-Division Multiplexing) Models
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfile(NetBoxModel):
    """WDM capability profile attached to a DeviceType."""

    device_type = models.OneToOneField(
        to="dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="wdm_profile",
        verbose_name=_("device type"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        ordering = ("device_type",)
        verbose_name = _("WDM device type profile")
        verbose_name_plural = _("WDM device type profiles")

    def __str__(self):
        """Return a label identifying this WDM profile."""
        return f"WDM Profile: {self.device_type}"

    def get_absolute_url(self):
        """Return the detail URL for this WDM device type profile."""
        return reverse("plugins:netbox_fms:wdmdevicetypeprofile", args=[self.pk])


class WdmChannelTemplate(NetBoxModel):
    """Channel slot template on a WdmDeviceTypeProfile."""

    profile = models.ForeignKey(
        to="netbox_fms.WdmDeviceTypeProfile",
        on_delete=models.CASCADE,
        related_name="channel_templates",
        verbose_name=_("profile"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port_template = models.ForeignKey(
        to="dcim.FrontPortTemplate",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("front port template"),
    )

    class Meta:
        ordering = ("profile", "grid_position")
        unique_together = (
            ("profile", "wavelength_nm"),
            ("profile", "grid_position"),
        )
        verbose_name = _("WDM channel template")
        verbose_name_plural = _("WDM channel templates")
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "front_port_template"],
                condition=models.Q(front_port_template__isnull=False),
                name="unique_profile_fpt",
            ),
        ]

    def __str__(self):
        """Return label and wavelength."""
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        """Return the detail URL for this WDM channel template."""
        return reverse("plugins:netbox_fms:wdmchanneltemplate", args=[self.pk])


class WdmNode(NetBoxModel):
    """WDM node instance attached to a Device."""

    device = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="wdm_node",
        verbose_name=_("device"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        ordering = ("device",)
        verbose_name = _("WDM node")
        verbose_name_plural = _("WDM nodes")

    def __str__(self):
        """Return device name with WDM prefix."""
        return f"WDM: {self.device.name}"

    def get_absolute_url(self):
        """Return the detail URL for this WDM node."""
        return reverse("plugins:netbox_fms:wdmnode", args=[self.pk])

    def save(self, *args, **kwargs):
        """Save and auto-populate channels from device type profile on creation."""
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.node_type != WdmNodeTypeChoices.AMPLIFIER:
            self._auto_populate_channels()

    def _auto_populate_channels(self):
        """Create WavelengthChannel rows from the device type's WDM profile templates."""
        from dcim.models import FrontPort

        try:
            profile = self.device.device_type.wdm_profile
        except WdmDeviceTypeProfile.DoesNotExist:
            return

        templates = list(profile.channel_templates.select_related("front_port_template").all())
        if not templates:
            return

        # Bulk-fetch all FrontPorts for this device, keyed by name
        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(device=self.device)}

        channels = []
        for ct in templates:
            front_port = None
            if ct.front_port_template:
                front_port = fp_by_name.get(ct.front_port_template.name)
            channels.append(
                WavelengthChannel(
                    wdm_node=self,
                    grid_position=ct.grid_position,
                    wavelength_nm=ct.wavelength_nm,
                    label=ct.label,
                    front_port=front_port,
                )
            )
        WavelengthChannel.objects.bulk_create(channels)


class WdmTrunkPort(NetBoxModel):
    """Maps a RearPort on a WDM node to a directional trunk."""

    wdm_node = models.ForeignKey(
        to="netbox_fms.WdmNode",
        on_delete=models.CASCADE,
        related_name="trunk_ports",
        verbose_name=_("WDM node"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.PROTECT,
        verbose_name=_("rear port"),
    )
    direction = models.CharField(max_length=50, verbose_name=_("direction"))
    position = models.PositiveIntegerField(verbose_name=_("position"))

    class Meta:
        ordering = ("wdm_node", "position")
        unique_together = (
            ("wdm_node", "rear_port"),
            ("wdm_node", "direction"),
        )
        verbose_name = _("WDM trunk port")
        verbose_name_plural = _("WDM trunk ports")

    def __str__(self):
        """Return direction and rear port."""
        return f"{self.direction}: {self.rear_port}"

    def get_absolute_url(self):
        """Return the detail URL for this WDM trunk port."""
        return reverse("plugins:netbox_fms:wdmtrunkport", args=[self.pk])


class WavelengthChannel(NetBoxModel):
    """A wavelength channel instance on a WDM node."""

    wdm_node = models.ForeignKey(
        to="netbox_fms.WdmNode",
        on_delete=models.CASCADE,
        related_name="channels",
        verbose_name=_("WDM node"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("front port"),
    )
    status = models.CharField(
        max_length=50,
        choices=WavelengthChannelStatusChoices,
        default=WavelengthChannelStatusChoices.AVAILABLE,
        verbose_name=_("status"),
    )

    class Meta:
        ordering = ("wdm_node", "grid_position")
        unique_together = (
            ("wdm_node", "wavelength_nm"),
            ("wdm_node", "grid_position"),
        )
        verbose_name = _("wavelength channel")
        verbose_name_plural = _("wavelength channels")
        constraints = [
            models.UniqueConstraint(
                fields=["wdm_node", "front_port"],
                condition=models.Q(front_port__isnull=False),
                name="unique_node_fp",
            ),
        ]

    def __str__(self):
        """Return label and wavelength."""
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        """Return the detail URL for this wavelength channel."""
        return reverse("plugins:netbox_fms:wavelengthchannel", args=[self.pk])


class WavelengthService(NetBoxModel):
    """An end-to-end wavelength service spanning one or more fiber circuits."""

    name = models.CharField(max_length=200, verbose_name=_("name"))
    status = models.CharField(
        max_length=50,
        choices=WavelengthServiceStatusChoices,
        default=WavelengthServiceStatusChoices.PLANNED,
        verbose_name=_("status"),
    )
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="wavelength_services",
        verbose_name=_("tenant"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    class Meta:
        ordering = ("name",)
        verbose_name = _("wavelength service")
        verbose_name_plural = _("wavelength services")

    def __str__(self):
        """Return the service name."""
        return self.name

    def get_absolute_url(self):
        """Return the detail URL for this wavelength service."""
        return reverse("plugins:netbox_fms:wavelengthservice", args=[self.pk])

    def clean(self):
        """Validate channel consistency: same grid, matching wavelength."""
        from decimal import Decimal

        super().clean()

        channel_assignments = self.channel_assignments.select_related("channel__wdm_node").all()
        if not channel_assignments.exists():
            return

        grids = set()
        svc_wl = Decimal(str(self.wavelength_nm))
        for ca in channel_assignments:
            if ca.channel:
                grids.add(ca.channel.wdm_node.grid)

        # Check grid consistency first
        if len(grids) > 1:
            raise ValidationError(
                _("All WDM nodes in a wavelength service must use the same grid. Found: %(grids)s")
                % {"grids": ", ".join(sorted(grids))}
            )

        # Then check wavelength consistency
        for ca in channel_assignments:
            if ca.channel:
                ch_wl = Decimal(str(ca.channel.wavelength_nm))
                if abs(ch_wl - svc_wl) > Decimal("0.01"):
                    raise ValidationError(
                        _("Channel %(label)s has wavelength %(ch_wl)s nm but service wavelength is %(svc_wl)s nm.")
                        % {
                            "label": ca.channel.label,
                            "ch_wl": ca.channel.wavelength_nm,
                            "svc_wl": self.wavelength_nm,
                        }
                    )

    def save(self, *args, **kwargs):
        """Save and handle lifecycle transitions (decommission releases channels)."""
        is_new = self._state.adding
        if not is_new:
            old = WavelengthService.objects.filter(pk=self.pk).values("status").first()
            old_status = old["status"] if old else None
        else:
            old_status = None

        super().save(*args, **kwargs)

        if not is_new and old_status != self.status:
            if self.status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                # Release channels and delete nodes
                self.nodes.all().delete()
                channel_ids = self.channel_assignments.values_list("channel_id", flat=True)
                WavelengthChannel.objects.filter(pk__in=channel_ids).update(
                    status=WavelengthChannelStatusChoices.AVAILABLE
                )
            elif old_status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                # Rebuild nodes from M2M
                self.rebuild_nodes()

    def get_stitched_path(self):
        """Return the stitched end-to-end path as an ordered list of hop dicts."""
        hops = []
        for ca in self.channel_assignments.select_related("channel__wdm_node__device").order_by("sequence"):
            if ca.channel:
                hops.append(
                    {
                        "type": "wdm_node",
                        "sequence": ca.sequence,
                        "node_id": ca.channel.wdm_node_id,
                        "node_name": ca.channel.wdm_node.device.name,
                        "channel_id": ca.channel_id,
                        "channel_label": ca.channel.label,
                        "wavelength_nm": float(ca.channel.wavelength_nm),
                    }
                )
        for fc in self.circuit_assignments.select_related("fiber_circuit").order_by("sequence"):
            if fc.fiber_circuit:
                hops.append(
                    {
                        "type": "fiber_circuit",
                        "sequence": fc.sequence,
                        "circuit_id": fc.fiber_circuit_id,
                        "circuit_name": fc.fiber_circuit.name,
                    }
                )
        hops.sort(key=lambda h: h["sequence"])
        for hop in hops:
            del hop["sequence"]
        return hops

    def rebuild_nodes(self):
        """Delete existing protection nodes and recreate from M2M assignments."""
        self.nodes.all().delete()
        nodes = []
        for ca in self.channel_assignments.all():
            if ca.channel_id:
                nodes.append(WavelengthServiceNode(service=self, channel=ca.channel))
        for fc in self.circuit_assignments.all():
            if fc.fiber_circuit_id:
                nodes.append(WavelengthServiceNode(service=self, fiber_circuit=fc.fiber_circuit))
        if nodes:
            WavelengthServiceNode.objects.bulk_create(nodes)


class WavelengthServiceCircuit(models.Model):
    """Through-model linking a WavelengthService to FiberCircuits in sequence."""

    service = models.ForeignKey(
        to="netbox_fms.WavelengthService",
        on_delete=models.CASCADE,
        related_name="circuit_assignments",
        verbose_name=_("service"),
    )
    fiber_circuit = models.ForeignKey(
        to="netbox_fms.FiberCircuit",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("fiber circuit"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("service", "sequence")
        unique_together = (
            ("service", "fiber_circuit"),
            ("service", "sequence"),
        )
        verbose_name = _("wavelength service circuit")
        verbose_name_plural = _("wavelength service circuits")

    def __str__(self):
        """Return service, sequence, and circuit."""
        return f"{self.service} #{self.sequence}: {self.fiber_circuit}"


class WavelengthServiceChannelAssignment(models.Model):
    """Through-model linking a WavelengthService to WavelengthChannels in sequence."""

    service = models.ForeignKey(
        to="netbox_fms.WavelengthService",
        on_delete=models.CASCADE,
        related_name="channel_assignments",
        verbose_name=_("service"),
    )
    channel = models.ForeignKey(
        to="netbox_fms.WavelengthChannel",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("channel"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("service", "sequence")
        unique_together = (
            ("service", "channel"),
            ("service", "sequence"),
        )
        verbose_name = _("wavelength service channel assignment")
        verbose_name_plural = _("wavelength service channel assignments")

    def __str__(self):
        """Return service, sequence, and channel."""
        return f"{self.service} #{self.sequence}: {self.channel}"


class WavelengthServiceNode(models.Model):
    """Relational index ensuring PROTECT-based deletion prevention for wavelength service references."""

    service = models.ForeignKey(
        to="netbox_fms.WavelengthService",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("service"),
    )
    fiber_circuit = models.ForeignKey(
        to="netbox_fms.FiberCircuit",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("fiber circuit"),
    )
    channel = models.ForeignKey(
        to="netbox_fms.WavelengthChannel",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("channel"),
    )

    class Meta:
        verbose_name = _("wavelength service node")
        verbose_name_plural = _("wavelength service nodes")
        constraints = [
            models.CheckConstraint(
                name="wsn_exactly_one_ref",
                condition=(
                    models.Q(fiber_circuit__isnull=False, channel__isnull=True)
                    | models.Q(fiber_circuit__isnull=True, channel__isnull=False)
                ),
            ),
            models.UniqueConstraint(
                fields=["service", "fiber_circuit"],
                condition=models.Q(fiber_circuit__isnull=False),
                name="unique_wsn_circuit",
            ),
            models.UniqueConstraint(
                fields=["service", "channel"],
                condition=models.Q(channel__isnull=False),
                name="unique_wsn_channel",
            ),
        ]

    def __str__(self):
        """Return the populated reference."""
        if self.fiber_circuit_id:
            return f"circuit: {self.fiber_circuit}"
        if self.channel_id:
            return f"channel: {self.channel}"
        return "empty node"
