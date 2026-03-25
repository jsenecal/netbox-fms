# Choice Values

These are the valid values for choice fields used throughout the FMS plugin. Use the **Value** column when setting fields via the REST API.

## ConstructionChoices

| Value | Label |
|-------|-------|
| loose_tube | Loose Tube |
| tight_buffer | Tight Buffer |
| ribbon | Ribbon |
| ribbon_in_tube | Ribbon-in-Tube |
| micro | Micro Cable |
| blown_fiber | Blown Fiber |

## FiberTypeChoices

| Value | Label | Group |
|-------|-------|-------|
| smf_os1 | SMF OS1 | Single-Mode |
| smf_os2 | SMF OS2 | Single-Mode |
| mmf_om1 | MMF OM1 | Multi-Mode |
| mmf_om2 | MMF OM2 | Multi-Mode |
| mmf_om3 | MMF OM3 | Multi-Mode |
| mmf_om4 | MMF OM4 | Multi-Mode |
| mmf_om5 | MMF OM5 | Multi-Mode |

## SheathMaterialChoices

| Value | Label |
|-------|-------|
| lszh | LSZH |
| pe | PE |
| mdpe | MDPE |
| hdpe | HDPE |
| pvc | PVC |
| pvdf | PVDF |

## ArmorTypeChoices

| Value | Label |
|-------|-------|
| steel_tape | Steel Tape |
| steel_wire | Steel Wire |
| corrugated_steel | Corrugated Steel |
| aluminum | Aluminum |
| dielectric | Dielectric |

## DeploymentChoices

| Value | Label | Group |
|-------|-------|-------|
| indoor | Indoor | Indoor |
| outdoor | Outdoor | Outdoor |
| direct_buried | Direct Buried | Outdoor |
| duct | Duct | Outdoor |
| microduct | Microduct | Outdoor |
| submarine | Submarine | Outdoor |
| aerial_adss | Aerial ADSS | Aerial |
| aerial_figure8 | Aerial Figure-8 | Aerial |
| aerial_lashed | Aerial Lashed | Aerial |
| indoor_outdoor | Indoor/Outdoor | Universal |

## FireRatingChoices

| Value | Label | Group |
|-------|-------|-------|
| ofnp | OFNP (Plenum) | NEC (North America) |
| ofnr | OFNR (Riser) | NEC (North America) |
| ofng | OFNG (General Purpose) | NEC (North America) |
| ofn | OFN (General Purpose) | NEC (North America) |
| cpr_aca | Aca (CPR) | CPR (Europe) |
| cpr_bca | Bca (CPR) | CPR (Europe) |
| cpr_cca | Cca (CPR) | CPR (Europe) |
| cpr_dca | Dca (CPR) | CPR (Europe) |
| cpr_eca | Eca (CPR) | CPR (Europe) |
| lszh | LSZH | Other |
| (empty) | None / Not Applicable | Other |

## CableElementTypeChoices

| Value | Label |
|-------|-------|
| strength_member | Strength Member |
| central_member | Central Strength Member |
| power_conductor | DC Power Conductor |
| tracer_wire | Tracer Wire |
| messenger_wire | Messenger Wire |
| ripcord | Ripcord |
| water_blocking | Water Blocking |

## SplicePlanStatusChoices

| Value | Label |
|-------|-------|
| draft | Draft |
| pending_approval | Pending Approval |
| approved | Approved |
| archived | Archived |

## FiberCircuitStatusChoices

| Value | Label |
|-------|-------|
| planned | Planned |
| staged | Staged |
| active | Active |
| decommissioned | Decommissioned |

## StorageMethodChoices

Used by the SlackLoop model to describe how excess fiber cable is stored.

| Value | Label |
|-------|-------|
| coil | Coil |
| figure_8 | Figure-8 |
| in_tray | In Tray |
| on_pole | On Pole |
| in_vault | In Vault |
