require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, Drilldown, DrilldownManager) {
    var users;
    var experiments;
    var accessClasses = {'Anon-Read':   'access_anonread',
                         'Read-Only':   'access_readonly',
                         'Read-Write':  'access_readwrite',
                         'Manage':      'access_manage',
                         'None':        'access_none',
                        };


    /*
     * refreshExperiments
     * Populator for experiments table.
     *
     * table - experiments table
     * selected_rows - irrelevant for experiments, can be ignored
     * is_instant - whether refresh should happen immediately or wait for
     *      another request
     * populateNextTableFn - callback to populate the next table in the
     *      drilldown sequence (see drilldown manager)
     */
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
                    data.data.map(function(d) { d.push(''); });
                    data.attrs.map(function(d) { delete d['class']; });
                    populateNextTableFn(table, data);
                    experiments.synchronizeSelections();
                    users.select();
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
                table.select(is_instant);
            },
        }); // ajax call
    };

    /*
     * removeHighlighting
     * Clear all highlighting from specified table.
     *
     * table - table to clear all highlighting from
     */
    var removeHighlighting = function(table)
    {
        var rows = table.getRows();
        rows.map(function(row) {
            row.children[row.children.length-1].textContent = '';
            for (var className in accessClasses)
            {
                if (accessClasses.hasOwnProperty(className))
                {
                    row.classList.remove(accessClasses[className]);
                }
            }
        });
    }

    /*
     * highlightRows
     * Highlights specified rows with corresponding access levels.
     *
     * rows - rows to highlight
     * access_levels - access levels to apply to rows (indexed by id of rows)
     */
    var highlightRows = function(rows, access_levels)
    {
        rows.map(function(row) {
            if (access_levels.hasOwnProperty(row.id))
            {
                row.classList.add(accessClasses[access_levels[row.id]]);
                row.children[row.children.length-1].textContent = access_levels[row.id];
            }
            else
            {
                row.classList.add('access_none');
            }
        });
    }

    /*
     * highlightAccess
     * Callback when a row is selected to update the highlighting on each table
     * to reflect the selection.
     */
    var highlightAccess = function(event)
    {
        var id;
        var table_to_change;
        var selected_rows = event.selected_rows;
        if (event.table === users && selected_rows.length == 1)
        {
            table_to_change = experiments;
            id = selected_rows[0].id.split('=')[1];
            url = "experiments/experiments_with_access";
            experiments.deselectAll();
        }
        else if (event.table === experiments && selected_rows.length == 1)
        {
            table_to_change = users;
            id = selected_rows[0].id.split('=')[1];
            url = "experiments/users_with_access";
            users.deselectAll();
        }

        removeHighlighting(users);
        removeHighlighting(experiments);

        if (table_to_change !== undefined)
        {
            exp_id = selected_rows[0].id.split('=')[1];
            $.ajax(
            {
                traditional: true,
                type: 'POST',
                url: url,
                data: { id: id },
                dataType: "json",
                success: function(data)
                {
                    if (data.success)
                    {
                        highlightRows(table_to_change.getRows(), data.access_levels);
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
            // do nothing
        }
    }

    /*
     * getAccessPrivileges
     * Requests and returns access privileges from server with an asynchrnous
     * call.
     */
    var getAccessPrivileges = function()
    {
        var access_priveleges;
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "experiments/get_access_privileges",
            dataType: "json",
            async: false,
            success: function(data)
            {
                access_privileges = data;
            },
        }); // ajax call
        return access_privileges;
    };

    /*
     * modifyAccess
     * Update access levels based on the selected users, experiments, and the
     * source table the rows were dragged from. For example, if 3 users are
     * selected and we drag them to a single experiment, user_ids would contain
     * the 3, exp_ids the 1, access_level the specified level, and dragged_from
     * would be the users table.
     *
     * user_ids - selected user ids
     * exp_ids - selected experiment ids
     * access_level - access level to set relevant rows to
     * dragged_from - table to update with the relevant new access levels when
     *      the transaction is complete
     */
    var modifyAccess = function(user_ids, exp_ids, access_level, dragged_from)
    {
        $.ajax(
        {
            traditional: true,
            type: 'POST',
            url: "experiments/modify_access",
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
                    dragged_from.select(true);
                    dragged_from.element.focus();
                }
            },
        }); // ajax call
    };

    /*
     * showAccessDialog
     * Pops up when rows have been dragged onto other rows to allow user to
     * choose what access level to grant.
     *
     * user_ids - selected user ids
     * exp_ids - selected experiment ids
     * dragged_from - table to update with the relevant new access levels when
     *      the transaction is complete
     */
    var showAccessDialog = function(user_ids, exp_ids, dragged_from)
    {
        $("#access_dialog").dialog({
            resizable:false,
            height:140,
            modal:true,
            buttons: {
                Okay: function() {
                    var access_level = $("#access_select").val();
                    modifyAccess(user_ids, exp_ids, access_level, dragged_from);
                    $(this).dialog("close");
                },
                Cancel: function() {
                    $(this).dialog("close");
                }
            }
        });
    };

    /*
     * dropAccessModification
     * Callback issued when rows are dropped onto other rows. Handles computing
     * the selected ids and relevant dragged_from table and selected access
     * privs.
     */
    var dropAccessModification = function(event, ui)
    {
        var experiments_table = $("#experiments .scrolltable_body table");
        var users_table = $("#users .scrolltable_body table");
        var dropped_onto_row = $(this);
        var dropped_onto_table = dropped_onto_row.closest('table');
        var dragged_row = $(event.target).closest('tr');
        var modify_experiments;
        var modify_users;
        var dragged_from;
        if (experiments_table.is(dropped_onto_table))
        {
            modify_users = dragged_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dragged_row;
            modify_experiments = dropped_onto_row.hasClass('ui-selected') ? experiments_table.find('.ui-selected') : dropped_onto_row;
            dragged_from = users;
        }
        else
        {
            modify_experiments = dragged_row.hasClass('ui-selected') ? experiments_table.find('.ui-selected') : dragged_row;
            modify_users = dropped_onto_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dropped_onto_row;
            dragged_from = experiments;
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
        showAccessDialog(user_ids, exp_ids, dragged_from);
    };

    /*
     * endsWith
     * Computes whether string ends with specified suffix.
     *
     * str - relevant string
     * suffix - suffix to search for
     */
    var endsWith = function(str, suffix)
    {
            return str.indexOf(suffix, str.length - suffix.length) !== -1;
    }

    /*
     * enableRefreshExperimentOnFormSubmit
     * Ensures experiments list is refreshed when the create experiment frame
     * has been updated.
     */
    var enableRefreshExperimentOnFormSubmit = function()
    {
        var iframe = document.getElementById("add_experiment_iframe");
        iframe.onload = function()
        {
            if (endsWith(iframe.contentWindow.location.pathname, "/experiment/create"))
            {
                dm.refresh(0);
            }
        }.bind(this);
    };

    var init = function()
    {
        users = new Drilldown("users", "Users");
        experiments = new Drilldown("experiments", "Experiments");
        users.resort();
        experiments.resort();
        new DrilldownManager([users], [], true);
        dm = new DrilldownManager([experiments], [refreshExperiments], true);

        TableDragAndDrop.setupDraggable($(users._getBodyTable()));
        TableDragAndDrop.setupDraggable($(experiments._getBodyTable()));
        TableDragAndDrop.setupDroppable($(users._getBodyTable()), $(experiments.getRows()), dropAccessModification);
        TableDragAndDrop.setupDroppable($(experiments._getBodyTable()), $(users.getRows()), dropAccessModification);

        $("#access_dialog").dialog();
        $("#access_dialog").dialog("destroy");

        users.onSelect(highlightAccess);
        experiments.onSelect(highlightAccess);

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
        enableRefreshExperimentOnFormSubmit();
    };

    $(document).ready(function() { init(); });
});
