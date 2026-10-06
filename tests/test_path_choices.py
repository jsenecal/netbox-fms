"""Choice metadata for fiber path analysis (#196) and the change queue."""

from netbox_fms.choices import (
    AssignmentBrokenReasonChoices,
    PathAnalysisReasonChoices,
    PathAnomalyKindChoices,
    PathCompletenessChoices,
    PathEndKindChoices,
    PathEndReasonChoices,
)


def test_completeness_is_derived_from_the_two_end_kinds():
    terminated, open_ = PathEndKindChoices.TERMINATED, PathEndKindChoices.OPEN
    assert PathCompletenessChoices.from_end_kinds(terminated, terminated) == "terminated_terminated"
    assert PathCompletenessChoices.from_end_kinds(terminated, open_) == "terminated_open"
    assert PathCompletenessChoices.from_end_kinds(open_, terminated) == "terminated_open"
    assert PathCompletenessChoices.from_end_kinds(open_, open_) == "open_open"


def test_end_reason_and_anomaly_values():
    assert PathEndReasonChoices.values() == ["unspliced", "cable_end"]
    assert PathAnomalyKindChoices.values() == ["too_many_connections", "loop", "dangling_reference"]
    assert AssignmentBrokenReasonChoices.values() == ["hops_changed", "path_lost"]


def test_analysis_reasons_cover_every_trigger():
    assert PathAnalysisReasonChoices.values() == [
        "cable_changed",
        "cable_deleted",
        "splice_changed",
        "port_mapping_changed",
        "strand_changed",
        "fault_changed",
        "closure_entry_changed",
        "bulk_operation",
    ]
