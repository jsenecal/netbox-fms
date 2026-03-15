from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.fields import ColorField

from .choices import (
    ArmorTypeChoices,
    CableElementTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberTypeChoices,
    FireRatingChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
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
    "FiberPathLoss",
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
        return f"{self.manufacturer} {self.model}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:fibercabletype", args=[self.pk])

    def clean(self):
        super().clean()

        # Armor type required if armored
        if self.is_armored and not self.armor_type:
            raise ValidationError({"armor_type": _("Armor type is required when cable is armored.")})
        if not self.is_armored and self.armor_type:
            raise ValidationError({"armor_type": _("Armor type should be blank when cable is not armored.")})

    def get_strand_count_from_templates(self):
        """Compute total fiber count from buffer tube templates."""
        total = self.buffer_tube_templates.aggregate(total=models.Sum("fiber_count"))["total"]
        return total or 0


class BufferTubeTemplate(NetBoxModel):
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
        return f"{self.fiber_cable_type} → {self.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:buffertubetemplate", args=[self.pk])

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


class RibbonTemplate(NetBoxModel):
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
        unique_together = ("fiber_cable_type", "buffer_tube_template", "name")
        verbose_name = _("ribbon template")
        verbose_name_plural = _("ribbon templates")

    def __str__(self):
        parent = self.buffer_tube_template or self.fiber_cable_type
        return f"{parent} → {self.name}"

    def get_absolute_url(self):
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


class CableElementTemplate(NetBoxModel):
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
        return f"{self.fiber_cable_type} → {self.name}"

    def get_absolute_url(self):
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
        return f"{self.cable} ({self.fiber_cable_type})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:fibercable", args=[self.pk])

    def save(self, *args, **kwargs):
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
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
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
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
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
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands",
        blank=True,
        null=True,
        verbose_name=_("front port"),
        help_text=_("The dcim FrontPort this strand has been provisioned to."),
    )

    class Meta:
        ordering = ("fiber_cable", "position")
        unique_together = ("fiber_cable", "position")
        verbose_name = _("fiber strand")
        verbose_name_plural = _("fiber strands")

    def __str__(self):
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
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
        return f"{self.fiber_cable.cable} → {self.name}"

    def get_absolute_url(self):
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
        return self.name

    def get_absolute_url(self):
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
        return self.name

    def get_absolute_url(self):
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

    class Meta:
        ordering = ("plan", "pk")
        unique_together = (
            ("plan", "fiber_a"),
            ("plan", "fiber_b"),
        )
        verbose_name = _("splice plan entry")
        verbose_name_plural = _("splice plan entries")

    def __str__(self):
        return f"{self.fiber_a} → {self.fiber_b}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:spliceplanentry", args=[self.pk])

    @property
    def is_inter_platter(self):
        """True if fiber_a and fiber_b are on different tray modules."""
        return self.fiber_a.module_id != self.fiber_b.module_id

    def clean(self):
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
        label = self.entrance_label or "\u2014"
        return f"{self.closure} \u2192 {label} ({self.fiber_cable})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:closurecableentry", args=[self.pk])


# ---------------------------------------------------------------------------
# Loss budget (stub)
# ---------------------------------------------------------------------------


class FiberPathLoss(NetBoxModel):
    """
    Loss measurement/calculation for a fiber cable segment.
    """

    cable = models.ForeignKey(
        to="dcim.Cable",
        on_delete=models.CASCADE,
        related_name="fiber_path_losses",
    )
    measured_loss_db = models.DecimalField(
        verbose_name=_("measured loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    calculated_loss_db = models.DecimalField(
        verbose_name=_("calculated loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    wavelength_nm = models.PositiveIntegerField(
        verbose_name=_("wavelength (nm)"),
    )
    test_date = models.DateField(
        verbose_name=_("test date"),
        blank=True,
        null=True,
    )
    otdr_file = models.FileField(
        verbose_name=_("OTDR file"),
        upload_to="otdr/",
        blank=True,
        null=True,
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("cable", "wavelength_nm")
        verbose_name = _("fiber path loss")
        verbose_name_plural = _("fiber path losses")

    def __str__(self):
        return f"{self.cable} @ {self.wavelength_nm}nm"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:fiberpathloss", args=[self.pk])
