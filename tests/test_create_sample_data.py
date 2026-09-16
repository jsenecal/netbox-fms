"""Regression tests for the create_sample_data management command.

Issue #56: the command drifted from the models after SlackLoop.length_unit
was replaced by FiberCableType.mark_unit (migration 0033) and crashed with
``TypeError: SlackLoop() got unexpected keyword arguments: 'length_unit'``.
A single smoke run of the command catches any constructor drift against the
current models.
"""

import re

import pytest
from django.core.management import call_command

from netbox_fms.models import FiberStrand, SlackLoop, SplicePlanEntry


@pytest.mark.django_db
class TestCreateSampleData:
    def test_simple_mode_completes_and_slack_loops_are_valid(self):
        call_command("create_sample_data", "--simple")

        loops = SlackLoop.objects.all()
        assert loops.exists()
        # Slack loops are bulk_create'd (no clean()); they must still validate
        # against the current model, which requires the cable type to declare
        # a mark_unit.
        for loop in loops:
            loop.full_clean()

        # Sample ports must use the shared write-once name grammar
        # ({cable.id}:F{absolute fiber number}), not a private copy of it.
        strand = FiberStrand.objects.select_related("fiber_cable", "front_port_a").first()
        fp = strand.front_port_a
        assert fp.name == f"{strand.fiber_cable.cable_id}:F{strand.position}"
        assert re.fullmatch(r"\d+:F\d+", fp.name)

        # The splice-plan builder groups tray ports via strand linkage, so
        # the demo plans actually carry entries under the pk-based names.
        assert SplicePlanEntry.objects.exists()
