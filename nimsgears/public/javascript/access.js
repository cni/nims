require(['./utility/tablednd', './utility/scrolltab_mgr'], function (TableDragAndDrop, ScrolltableManager) {
    var users;
    var experiments;
    var current_access;

    var refreshCurrentAccess = function(event)
    {
        if (event.selected_rows.length == 1)
        {
            exp_id = event.selected_rows.attr('id').split('_')[1];
            $.ajax(
            {
                traditional: true,
                type: 'POST',
                url: "users_with_access",
                data: { exp_id: exp_id },
                dataType: "json",
                async: false,
                success: function(data)
                {
                    if (data.success)
                    {
                        current_access.populateTable(data);
                    }
                },
            }); // ajax call
        }
    }

    var getAccessPrivileges = function()
    {
        var access_priveleges;
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "get_access_privileges",
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
            url: "modify_access",
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
            exp_ids.push(this.id.split('_')[1]);
        });
        showAccessDialog(user_ids, exp_ids);
    };

    var init = function()
    {
        ScrolltableManager.init();
        ScrolltableManager.setTableHeights();
        ScrolltableManager.autoSetTableHeights();

        ScrolltableManager.resortAll();

        users = ScrolltableManager.getById("users");
        experiments = ScrolltableManager.getById("experiments");
        current_access = ScrolltableManager.getById("current_access");

        users.setClickEvents();
        experiments.setClickEvents();
        experiments.onSelect(refreshCurrentAccess);

        var users_table = $("#users .scrolltable_body table");
        var experiments_table = $("#experiments .scrolltable_body table");

        TableDragAndDrop.setupDraggable(users_table);
        TableDragAndDrop.setupDraggable(experiments_table);
        TableDragAndDrop.setupDroppable("#users .scrolltable_body table", experiments.getRows(), dropAccessModification);
        TableDragAndDrop.setupDroppable("#experiments .scrolltable_body table", users.getRows(), dropAccessModification);
        TableDragAndDrop.setupMultiDrop(users_table);
        TableDragAndDrop.setupMultiDrop(experiments_table);

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
