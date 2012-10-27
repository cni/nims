require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, Drilldown, DrilldownManager) {
    var users;
    var experiments;
    var current_access;

    var refreshExperiments = function(table, selected_rows, is_instant, populateNextTableFn)
    {
        $.ajax(
        {
            type: 'POST',
            url: "browse/list_query",
            dataType: "json",
            data: { exp_list: true },
            success: function(data)
            {
                var row;
                if (data.success)
                {
                    populateNextTableFn(table, data);
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
                table.select(is_instant);
            },
        }); // ajax call
    };

    var refreshCurrentAccess = function(table, selected_rows, is_instant, populateNextTableFn)
    {
        if (selected_rows && selected_rows.length == 1)
        {
            exp_id = selected_rows[0].id.split('=')[1];
            $.ajax(
            {
                traditional: true,
                type: 'POST',
                url: "access/users_with_access",
                data: { exp_id: exp_id },
                dataType: "json",
                success: function(data)
                {
                    if (data.success)
                    {
                        populateNextTableFn(table, data);
                    }
                    else
                    {
                        alert('Failed');
                    } // implement better alert TODO
                },
            }); // ajax call
        }
        else
        {
            populateNextTableFn(table, []);
        }
    }

    var getAccessPrivileges = function()
    {
        var access_priveleges;
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "access/get_access_privileges",
            dataType: "json",
            async: false,
            success: function(data)
            {
                access_privileges = data;
            },
        }); // ajax call
        return access_privileges;
    };

    var modifyAccess = function(user_ids, exp_ids, access_level)
    {
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "access/modify_access",
            dataType: "json",
            data:
            {
                user_ids: user_ids,
                exp_ids: exp_ids,
                access_level: access_level
            },
            success: function(data)
            {
                if (!data.success)
                {
                    alert('Failed'); // implement better alert
                } else {
                    experiments.select(true);
                    experiments.element.focus();
                }
            },
        }); // ajax call
    };

    var showAccessDialog = function(user_ids, exp_ids, access_level)
    {
        $("#access_dialog").dialog({
            resizable:false,
            height:140,
            modal:true,
            buttons: {
                Okay: function() {
                    var access_level = $("#access_select").val();
                    modifyAccess(user_ids, exp_ids, access_level);
                    $(this).dialog("close");
                },
                Cancel: function() {
                    $(this).dialog("close");
                }
            }
        });
    };

    var dropAccessModification = function(event, ui)
    {
        var experiments_table = $("#experiments .scrolltable_body table");
        var users_table = $("#users .scrolltable_body table");
        var dropped_onto_row = $(this);
        var dropped_onto_table = dropped_onto_row.closest('table');
        var dragged_row = $(event.target).closest('tr');
        var modify_experiments;
        var modify_users;
        if (experiments_table.is(dropped_onto_table))
        {
            modify_users = dragged_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dragged_row;
            modify_experiments = dropped_onto_row.hasClass('ui-selected') ? experiments_table.find('.ui-selected') : dropped_onto_row;
        }
        else
        {
            modify_experiments = dragged_row.hasClass('ui-selected') ? experiments_table.find('.ui-selected') : dragged_row;
            modify_users = dropped_onto_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dropped_onto_row;
        }
        var exp_ids = new Array();
        var user_ids = new Array();
        modify_users.each(function()
        {
            user_ids.push(this.children[0].textContent);
        });
        modify_experiments.each(function ()
        {
            exp_ids.push(this.id.split('=')[1]);
        });
        showAccessDialog(user_ids, exp_ids);
    };

    var init = function()
    {
        users = new Drilldown("users", "Users");
        experiments = new Drilldown("experiments", "Experiments");
        users.resort();
        experiments.resort();
        current_access = new Drilldown("current_access", "Current Access");
        new DrilldownManager([users], [], true);
        new DrilldownManager([experiments, current_access], [refreshExperiments, refreshCurrentAccess], true);

        TableDragAndDrop.setupDraggable($(users._getBodyTable()));
        TableDragAndDrop.setupDraggable($(experiments._getBodyTable()));
        TableDragAndDrop.setupDroppable($(users._getBodyTable()), $(experiments.getRows()), dropAccessModification);
        TableDragAndDrop.setupDroppable($(experiments._getBodyTable()), $(users.getRows()), dropAccessModification);
        TableDragAndDrop.setupMultiDrop($(users._getBodyTable()));
        TableDragAndDrop.setupMultiDrop($(experiments._getBodyTable()));

        $("#access_dialog").dialog();
        $("#access_dialog").dialog("destroy");

        var access_privileges = getAccessPrivileges();
        access_privileges.push("Remove Access");
        var option;
        var selector = $("#access_select");
        access_privileges.forEach(function(item)
        {
            option = document.createElement('option');
            option.textContent = item;
            selector.append(option);
        });
    };

    $(function() {
        init();
    });
});
