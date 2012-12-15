require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, Drilldown, DrilldownManager) {
    var pis;
    var admins;
    var members;
    var others;

    var pis_mgr;
    var admins_mgr;
    var members_mgr;
    var others_mgr;

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
                url: "groups/groups_query",
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
        admins = new Drilldown("admins", "Administrators");
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
