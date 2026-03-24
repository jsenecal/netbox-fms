from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="FMS",
    groups=(
        (
            "Cable Types",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercabletype_list",
                    link_text="Fiber Cable Types",
                    permissions=["netbox_fms.view_fibercabletype"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercabletype_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercabletype"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercabletype_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercabletype"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:buffertubetemplate_list",
                    link_text="Buffer Tube Templates",
                    permissions=["netbox_fms.view_buffertubetemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:buffertubetemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_buffertubetemplate"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:ribbontemplate_list",
                    link_text="Ribbon Templates",
                    permissions=["netbox_fms.view_ribbontemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:ribbontemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_ribbontemplate"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:cableelementtemplate_list",
                    link_text="Cable Element Templates",
                    permissions=["netbox_fms.view_cableelementtemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:cableelementtemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_cableelementtemplate"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Fiber Cables",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercable_list",
                    link_text="Fiber Cables",
                    permissions=["netbox_fms.view_fibercable"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercable_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercable"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercable_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercable"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Slack Loops",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:slackloop_list",
                    link_text="Slack Loops",
                    permissions=["netbox_fms.view_slackloop"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:slackloop_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_slackloop"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:slackloop_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_slackloop"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Circuits",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercircuit_list",
                    link_text="Fiber Circuits",
                    permissions=["netbox_fms.view_fibercircuit"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercircuit_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercircuit"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercircuit_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercircuit"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercircuitpath_list",
                    link_text="Fiber Circuit Paths",
                    permissions=["netbox_fms.view_fibercircuitpath"],
                ),
            ),
        ),
        (
            "Splice Planning",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceproject_list",
                    link_text="Splice Projects",
                    permissions=["netbox_fms.view_spliceproject"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:spliceproject_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_spliceproject"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceplan_list",
                    link_text="Splice Plans",
                    permissions=["netbox_fms.view_spliceplan"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:spliceplan_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_spliceplan"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceplanentry_list",
                    link_text="Splice Plan Entries",
                    permissions=["netbox_fms.view_spliceplanentry"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:closurecableentry_list",
                    link_text="Closure Cable Entries",
                    permissions=["netbox_fms.view_closurecableentry"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:closurecableentry_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_closurecableentry"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:trayprofile_list",
                    link_text="Tray Profiles",
                    permissions=["netbox_fms.view_trayprofile"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:trayprofile_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_trayprofile"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:tubeassignment_list",
                    link_text="Tube Assignments",
                    permissions=["netbox_fms.view_tubeassignment"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:tubeassignment_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_tubeassignment"],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-arrow-decision-outline",
)
