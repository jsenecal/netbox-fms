from utilities.choices import ChoiceSet

#
# FiberCableType choices
#


class ConstructionChoices(ChoiceSet):
    LOOSE_TUBE = "loose_tube"
    TIGHT_BUFFER = "tight_buffer"
    RIBBON = "ribbon"
    RIBBON_IN_TUBE = "ribbon_in_tube"
    MICRO = "micro"
    BLOWN_FIBER = "blown_fiber"

    CHOICES = (
        (LOOSE_TUBE, "Loose Tube"),
        (TIGHT_BUFFER, "Tight Buffer"),
        (RIBBON, "Ribbon"),
        (RIBBON_IN_TUBE, "Ribbon-in-Tube"),
        (MICRO, "Micro Cable"),
        (BLOWN_FIBER, "Blown Fiber"),
    )


class FiberTypeChoices(ChoiceSet):
    SMF_OS1 = "smf_os1"
    SMF_OS2 = "smf_os2"
    MMF_OM1 = "mmf_om1"
    MMF_OM2 = "mmf_om2"
    MMF_OM3 = "mmf_om3"
    MMF_OM4 = "mmf_om4"
    MMF_OM5 = "mmf_om5"

    CHOICES = (
        (
            "Single-Mode",
            (
                (SMF_OS1, "SMF OS1"),
                (SMF_OS2, "SMF OS2"),
            ),
        ),
        (
            "Multi-Mode",
            (
                (MMF_OM1, "MMF OM1"),
                (MMF_OM2, "MMF OM2"),
                (MMF_OM3, "MMF OM3"),
                (MMF_OM4, "MMF OM4"),
                (MMF_OM5, "MMF OM5"),
            ),
        ),
    )


class SheathMaterialChoices(ChoiceSet):
    LSZH = "lszh"
    PE = "pe"
    MDPE = "mdpe"
    HDPE = "hdpe"
    PVC = "pvc"
    PVDF = "pvdf"

    CHOICES = (
        (LSZH, "LSZH"),
        (PE, "PE"),
        (MDPE, "MDPE"),
        (HDPE, "HDPE"),
        (PVC, "PVC"),
        (PVDF, "PVDF"),
    )


class ArmorTypeChoices(ChoiceSet):
    STEEL_TAPE = "steel_tape"
    STEEL_WIRE = "steel_wire"
    CORRUGATED_STEEL = "corrugated_steel"
    ALUMINUM = "aluminum"
    DIELECTRIC = "dielectric"

    CHOICES = (
        (STEEL_TAPE, "Steel Tape"),
        (STEEL_WIRE, "Steel Wire"),
        (CORRUGATED_STEEL, "Corrugated Steel"),
        (ALUMINUM, "Aluminum"),
        (DIELECTRIC, "Dielectric"),
    )


class DeploymentChoices(ChoiceSet):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    INDOOR_OUTDOOR = "indoor_outdoor"
    AERIAL_ADSS = "aerial_adss"
    AERIAL_FIGURE8 = "aerial_figure8"
    AERIAL_LASHED = "aerial_lashed"
    DIRECT_BURIED = "direct_buried"
    DUCT = "duct"
    MICRODUCT = "microduct"
    SUBMARINE = "submarine"

    CHOICES = (
        (
            "Indoor",
            ((INDOOR, "Indoor"),),
        ),
        (
            "Outdoor",
            (
                (OUTDOOR, "Outdoor"),
                (DIRECT_BURIED, "Direct Buried"),
                (DUCT, "Duct"),
                (MICRODUCT, "Microduct"),
                (SUBMARINE, "Submarine"),
            ),
        ),
        (
            "Aerial",
            (
                (AERIAL_ADSS, "Aerial ADSS"),
                (AERIAL_FIGURE8, "Aerial Figure-8"),
                (AERIAL_LASHED, "Aerial Lashed"),
            ),
        ),
        (
            "Universal",
            ((INDOOR_OUTDOOR, "Indoor/Outdoor"),),
        ),
    )


class FireRatingChoices(ChoiceSet):
    OFNR = "ofnr"
    OFNP = "ofnp"
    OFN = "ofn"
    OFNG = "ofng"
    LSZH = "lszh"
    CPR_ACA = "cpr_aca"
    CPR_BCA = "cpr_bca"
    CPR_CCA = "cpr_cca"
    CPR_DCA = "cpr_dca"
    CPR_ECA = "cpr_eca"
    NONE = ""

    CHOICES = (
        (
            "NEC (North America)",
            (
                (OFNP, "OFNP (Plenum)"),
                (OFNR, "OFNR (Riser)"),
                (OFNG, "OFNG (General Purpose)"),
                (OFN, "OFN (General Purpose)"),
            ),
        ),
        (
            "CPR (Europe)",
            (
                (CPR_ACA, "Aca (CPR)"),
                (CPR_BCA, "Bca (CPR)"),
                (CPR_CCA, "Cca (CPR)"),
                (CPR_DCA, "Dca (CPR)"),
                (CPR_ECA, "Eca (CPR)"),
            ),
        ),
        (
            "Other",
            (
                (LSZH, "LSZH"),
                (NONE, "None / Not Applicable"),
            ),
        ),
    )


#
# Cable element choices
#


class CableElementTypeChoices(ChoiceSet):
    STRENGTH_MEMBER = "strength_member"
    CENTRAL_MEMBER = "central_member"
    POWER_CONDUCTOR = "power_conductor"
    TRACER_WIRE = "tracer_wire"
    MESSENGER_WIRE = "messenger_wire"
    RIPCORD = "ripcord"
    WATER_BLOCKING = "water_blocking"

    CHOICES = (
        (STRENGTH_MEMBER, "Strength Member"),
        (CENTRAL_MEMBER, "Central Strength Member"),
        (POWER_CONDUCTOR, "DC Power Conductor"),
        (TRACER_WIRE, "Tracer Wire"),
        (MESSENGER_WIRE, "Messenger Wire"),
        (RIPCORD, "Ripcord"),
        (WATER_BLOCKING, "Water Blocking"),
    )


#
# Splice plan choices
#


class FiberCircuitStatusChoices(ChoiceSet):
    PLANNED = "planned"
    STAGED = "staged"
    ACTIVE = "active"
    DECOMMISSIONED = "decommissioned"

    CHOICES = (
        (PLANNED, "Planned"),
        (STAGED, "Staged"),
        (ACTIVE, "Active"),
        (DECOMMISSIONED, "Decommissioned"),
    )


class SplicePlanStatusChoices(ChoiceSet):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"

    CHOICES = (
        (DRAFT, "Draft"),
        (PENDING_REVIEW, "Pending Review"),
        (READY_TO_APPLY, "Ready to Apply"),
        (APPLIED, "Applied"),
    )
