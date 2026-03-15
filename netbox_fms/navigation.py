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
            ),
        ),
        (
            "Loss Budget",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fiberpathloss_list",
                    link_text="Fiber Path Losses",
                    permissions=["netbox_fms.view_fiberpathloss"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fiberpathloss_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fiberpathloss"],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-arrow-decision-outline",
)
