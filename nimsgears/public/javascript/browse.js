require(['./utility/tablednd', './utility/scrolltab_mgr'], function (TableDragAndDrop, ScrolltableManager) {
    var experiments;
    var sessions;
    var epochs;

    var toggleObject = function (object, makeVisible, callback)
    {
        objectVisible = object.css('display') != 'none';
        if ((makeVisible & !objectVisible) || (!makeVisible & objectVisible))
        {
            object.toggle('slide', null, 150, callback);
        }
        else
        {
            if (callback) callback();
        }
    };

    var getIdDictionary = function (selected_rows)
    {
        var id_dict = {};
        selected_rows.each(function()
        {
            var chunks = this.id.split('_');
            var key = chunks[0];
            if (id_dict[key] == null)
            {
                id_dict[key] = new Array();
            }
            id_dict[key].push(chunks[1]);
        });
        return id_dict;
    };

    var dropDownloads = function (event, ui)
    {
        var selected_rows;
        selected_rows = ui.helper.data('moving_rows');

        var id_dict = getIdDictionary(selected_rows);
        console.log(id_dict);
        alert(id_dict);
        /*
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "download",
            dataType: "json",
            data:
            {
                id_dict: id_dict
            },
        });
        */
    };

    var dropTrash = function (event, ui)
    {
        var selected_rows;
        selected_rows = ui.helper.data('moving_rows');

        var id_dict = getIdDictionary(selected_rows);
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "trash",
            dataType: "json",
            data:
            {
                exp: id_dict['exp'],
                sess: id_dict['sess'],
                epoch: id_dict['epoch'],
            },
            success: function(data)
            {
                if (data.success)
                {
                    labelTrash(selected_rows, getTrashFlag(), data.untrashed);
                }
                else
                {
                    alert('Failed');
                }
            },
        });
    };

    var dropSessionsOnExperiment = function(event, ui)
    {
        var selected_rows;
        selected_rows = ui.helper.data('moving_rows');

        var sess_id_list = Array();
        selected_rows.each(function() { sess_id_list.push(this.id.split('_')[1]); });
        var target_exp_id = this.id.split("_")[1];
        var target_exp_row = $(this);
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "transfer_sessions",
            dataType: "json",
            data:
            {
                sess_id_list: sess_id_list,
                exp_id: target_exp_id
            },
            success: function(data)
            {
                    if (data.success)
                    {
                        selected_rows.remove();
                        $("#sessions .scrolltable_body tbody tr").removeClass('stripe');
                        $("#sessions .scrolltable_body tbody tr:odd").addClass('stripe');
                        if (selected_rows.length == 1 && selected_rows.first().hasClass("ui-selected"))
                        {
                            refreshEpochs(null);
                        }
                        if (data.untrashed)
                        {
                            target_exp_row.removeClass('trash');
                        }
                    }
                    else
                    {
                        alert("Transfer failed to commit.");
                    }
            },
        });
    };

    var getTrashFlag = function()
    {
        var trash_flag;
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "get_trash_flag",
            dataType: "json",
            async: false,
            success: function(data)
            {
                trash_flag = data;
            },
        });
        return trash_flag;
    };

    var changeTrashFlag = function(event, ui)
    {
        var trash_flag = this.id.split('_')[1];
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "set_trash_flag",
            dataType: "json",
            data:
            {
                trash_flag: trash_flag
            },
            success: function(data)
            {
                if (data.success)
                {
                    refreshExperiments();
                }
                else
                {
                    alert('Failed');
                }
            },
        });
    };

    var refreshExperiments = function()
    {
        var table_body = experiments.getBody();
        $.ajax(
        {
            type: 'POST',
            url: "list_query",
            dataType: "json",
            data: { exp_list: true },
            success: function(data)
            {
                var row;
                if (data.success)
                {
                    experiments.populateTable(data);
                    experiments.setClickEvents();
                    TableDragAndDrop.setupDroppable(sessions.getBody().closest('table'), experiments.getRows(), dropSessionsOnExperiment);
                }
                else
                {
                    alert('Failed'); // implement better alert
                }

            },
        }); // ajax call
    };

    var refreshSessions = function(experiment_row)
    {
        var table_body = sessions.getBody();
        if (experiment_row && experiment_row.length == 1) // make sure we didn't just get passed an empty list
        {
            var exp_id = experiment_row.attr('id').split('_')[1];
            $.ajax(
            {
                type: 'POST',
                url: "list_query",
                dataType: "json",
                data: { sess_list: exp_id },
                success: function(data)
                {
                    if (data.success)
                    {
                        epochs.refresh(null);

                        sessions.populateTable(data);
                        sessions.setClickEvents();

                        // Disable rows that you don't have manage access to
                        var experiment_rows = experiments.getRows();
                        if (experiment_row.hasClass('access_mg'))
                        {
                            experiment_rows.each(function()
                            {
                                var disable_drop = !$(this).hasClass('access_mg') || $(this).is(experiment_row);
                                $(this).droppable("option", "disabled", disable_drop);
                            });
                        }
                        else
                        {
                            experiment_rows.droppable("option", "disabled", true);
                        }
                        toggleObject(table_body.closest('table'), true, null);
                    }
                    else
                    {
                        alert('Failed');
                    } // implement better alert TODO

                },
            });
        }
        else
        {
            sessions.updateSelectedRows();
            toggleObject(epochs.getBody().closest('table'), false, function()
            {
                toggleObject(table_body.closest('table'), false, null);
            });
        }
    };

    var refreshEpochs = function(session_row)
    {
        var table_body = epochs.getBody();
        if (session_row && session_row.length == 1) // make sure we didn't get passed an empty list
        {
            var sess_id = session_row.attr('id').split('_')[1];
            $.ajax(
            {
                type: 'POST',
                url: "list_query",
                dataType: "json",
                data: { epoch_list: sess_id },
                success: function(data)
                {
                    if (data.success)
                    {
                        epochs.populateTable(data);
                    }
                    else
                    {
                        alert('Failed'); // implement better alert
                    }

                    toggleObject(table_body.closest('table'), true, null);
                    epochs.setClickEvents();
                },
            }); // ajax call
        }
        else
        {
            toggleObject(table_body.closest('table'), false, null);
        }
    };

    var init = function()
    {
        ScrolltableManager.init();
        ScrolltableManager.setTableHeights();
        ScrolltableManager.autoSetTableHeights();
        experiments = ScrolltableManager.getById("experiments");
        sessions = ScrolltableManager.getById("sessions");
        epochs = ScrolltableManager.getById("epochs");

        experiments.onRefresh(refreshExperiments);
        sessions.onRefresh(refreshSessions);
        epochs.onRefresh(refreshEpochs);

        experiments.onSelect(refreshSessions);
        sessions.onSelect(refreshEpochs);

        experiments.refresh();

        var sessions_table = $("#sessions .scrolltable_body table");
        var experiments_table = $("#experiments .scrolltable_body table");
        var epochs_table = $("#epochs .scrolltable_body table");
        var experiments_rows = $("#experiments .scrolltable_body tbody tr");

        TableDragAndDrop.setupDraggable(sessions_table);
        TableDragAndDrop.setupDraggable(experiments_table);
        TableDragAndDrop.setupDraggable(epochs_table);
        TableDragAndDrop.setupDroppable("#sessions .scrolltable_body table", sessions_table, $("#download_drop"), dropDownloads);
        TableDragAndDrop.setupDroppable(".scrolltable_body table", $("#trash_drop"), dropTrash);

        $("#radio_trash input").change(changeTrashFlag);
        $($("#radio_trash input")[getTrashFlag()]).click();
    };

    $(function() {
        init();
    });
});
