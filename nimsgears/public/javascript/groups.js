require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, Drilldown, DrilldownManager) {
    var pis;
    var admins;
    var members;
    var others;

    var pis_mgr;
    var admins_mgr;
    var members_mgr;
    var others_mgr;

    /*
     * showRetroDialog
     * Displays dialog to confirm whether user would like to apply permissions
     * changes retroactively or only for future experiments.
     */
    var showRetroDialog = function(user_ids, group_id, membership_src, membership_dst)
    {
        $("#retro_dialog").dialog({
            resizable:false,
            height:140,
            modal:true,
            buttons: {
                "Yes": function() {
                    modifyGroups(user_ids, group_id, membership_src, membership_dst, true);
                    $(this).dialog("close");
                },
                "No": function() {
                    modifyGroups(user_ids, group_id, membership_src, membership_dst, false);
                    $(this).dialog("close");
                }
            }
        });
    };

    /*
     * modifyGroups
     * Issues server call to modify group privileges.
     *
     * user_ids - user ids that are being modified
     * membership_src - source group (losing these privileges)
     * membership_dst - destination group (gaining these privileges)
     * is_retroactive - whether to apply to all past relevant experiments or
     *      only future
     */
    var modifyGroups = function(user_ids, group_id, membership_src, membership_dst, is_retroactive)
    {
        console.log(is_retroactive);
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "groups/modify_groups",
            dataType: "json",
            data:
            {
                user_ids: user_ids,
                group_id: group_id,
                membership_src: membership_src,
                membership_dst: membership_dst,
                is_retroactive: is_retroactive
            },
            success: function(data)
            {
                if (data['success'])
                {
                    refreshGroups(group_id);
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
            },
        }); // ajax call
    };

    /*
     * dropUsersOnGroup
     * Callback fired when users are dragged from one group to another.
     * Computes all relevant ids, membership sources and destinations, as well
     * as creating the popup to determine whether changes should be retroactive
     * or not.
     */
    var dropUsersOnGroup = function(event, ui)
    {
        var group_id = $("#group_select").val();
        var dropped_onto_div = $(this);
        var dragged_row = $(event.target).closest('tr');
        var dragged_from_table = dragged_row.closest('table');
        var user_rows;
        var user_ids = new Array();
        var membership_src = dragged_from_table.data("moving_rows").closest(".scrolltable_wrapper").attr("id");
        var membership_dst = dropped_onto_div.closest('.scrolltable_wrapper').attr('id');

        user_rows = dragged_row.hasClass('ui-selected') ? dragged_from_table.find('.ui-selected') : dragged_row;
        user_rows.each(function()
        {
            user_ids.push(this.children[0].textContent);
            // TODO do this with an id on the rows instead of just using first TD -
            // probably more robust
        });
        showRetroDialog(user_ids, group_id, membership_src, membership_dst);
    };

    /*
     * refreshGroups
     * Repopulates all tables with the selected research groups members (pi,
     * admins, etc).
     *
     * research_group - group whose members we're requesting
     */
    var refreshGroups = function(research_group)
    {
        pis.startLoading();
        admins.startLoading();
        members.startLoading();
        others.startLoading();
        if (research_group)
        {
            $.ajax(
            {
                type: 'POST',
                url: "groups/members_query",
                dataType: "json",
                data:
                {
                    research_group: research_group
                },
                success: function(data)
                {
                    pis_mgr.getPopulateNextTable()(pis, data.pis);
                    admins_mgr.getPopulateNextTable()(admins, data.admins);
                    members_mgr.getPopulateNextTable()(members, data.members);
                    others_mgr.getPopulateNextTable()(others, data.others);
                },
            }); // ajax call
        }
    };

    var init = function()
    {
        pis = new Drilldown("pis", "Principal Investigators");
        admins = new Drilldown("admins", "Managers");
        members = new Drilldown("members", "Members");
        others = new Drilldown("others", "Non-Members");

        pis_mgr = new DrilldownManager([pis], [], true);
        admins_mgr = new DrilldownManager([admins], [], true);
        members_mgr = new DrilldownManager([members], [], true);
        others_mgr = new DrilldownManager([others], [], true);

        var first_group;
        if (first_group = $("#group_select").children().first())
        {
            refreshGroups(first_group.text());
        }

        $("#group_select").change(function() { refreshGroups(this.value); });

        TableDragAndDrop.setupDraggable($(".scrolltable_body table"));
        TableDragAndDrop.setupDroppable(function(droppable)
        {
            return droppable.is('table') && droppable.closest('.scrolltable_wrapper').attr('id') != $(this).closest('.scrolltable_wrapper').attr('id');
        }, $(".scrolltable_body"), dropUsersOnGroup);

        $("#retro_dialog").dialog();
        $("#retro_dialog").dialog("destroy");
    };

    $(function() {
        init();
    });
});
