require(['./utility/tablednd', './utility/scrolltab_mgr'], function (TableDragAndDrop, ScrolltableManager) {
    var experiments;
    var sessions;
    var epochs;
    var datasets;

    var experiments_popup;
    var sessions_popup;
    var epochs_popup;
    var datasets_popup;

    var getId = function(string)
    {
        return string.split("_")[1];
    };

    var toggleObject = function (object, makeVisible)
    {
        objectVisible = object.css('display') != 'none';
        if (makeVisible & !objectVisible)
        {
            object.show();
        }
        else if (!makeVisible & objectVisible)
        {
            object.hide();
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
            url: "browse/trash",
            dataType: "json",
            data:
            {
                exp: id_dict['exp'],
                sess: id_dict['sess'],
                epoch: id_dict['epoch'],
                dataset: id_dict['dataset'],
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

    var dropSessionsOnExperiment = function(event, ui)
    {
        var selected_rows;
        selected_rows = ui.helper.data('moving_rows');

        var sess_id_list = Array();
        selected_rows.each(function() { sess_id_list.push(getId(this.id)); });
        var target_exp_id = getId(this.id);
        var target_exp_row = $(this);
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "browse/transfer_sessions",
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
            url: "browse/get_trash_flag",
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
        var trash_flag = getId(this.id);
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "browse/set_trash_flag",
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
        experiments.startLoading();
        var table_body = experiments.getBody();
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
                    experiments.populateTable(data);
                    experiments.synchronizeSelections();
                    experiments.setClickEvents();
                    experiments.onDoubleClick(function() { showDialog(experiments_popup, { exp_id: getId(this.id) }); });
                    TableDragAndDrop.setupDroppable(sessions.getBody().closest('table'), experiments.getRows(), dropSessionsOnExperiment);
                    refreshSessions(
                    {
                        selected_rows: experiments.getSelectedRows()
                    });
                    experiments.stopLoading();
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
            },
        }); // ajax call
    };

    var refreshSessions = function(event)
    {
        sessions.startLoading();
        var experiment_row = event ? event.selected_rows : null;
        var table_body = sessions.getBody();
        if (experiment_row && experiment_row.length == 1) // make sure we didn't just get passed an empty list
        {
            var exp_id = getId(experiment_row.attr('id'));
            $.ajax(
            {
                type: 'POST',
                url: "browse/list_query",
                dataType: "json",
                data: { sess_list: exp_id },
                success: function(data)
                {
                    if (data.success)
                    {
                        sessions.populateTable(data);
                        sessions.synchronizeSelections();
                        sessions.setClickEvents();
                        sessions.onDoubleClick(function() { showDialog(sessions_popup, { sess_id: getId(this.id) }); });

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
                        toggleObject(table_body.closest('table'), true);
                        refreshEpochs(
                        {
                            selected_rows: sessions.getSelectedRows()
                        });
                        sessions.stopLoading();
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
            toggleObject(datasets.getBody().closest('table'), false);
            toggleObject(epochs.getBody().closest('table'), false);
            toggleObject(table_body.closest('table'), false);
            sessions.stopLoading();
        }
    };

    var refreshEpochs = function(event)
    {
        epochs.startLoading();
        var session_row = event ? event.selected_rows : null;
        var table_body = epochs.getBody();
        if (session_row && session_row.length == 1) // make sure we didn't get passed an empty list
        {
            var sess_id = getId(session_row.attr('id'));
            $.ajax(
            {
                type: 'POST',
                url: "browse/list_query",
                dataType: "json",
                data: { epoch_list: sess_id },
                success: function(data)
                {
                    if (data.success)
                    {
                        epochs.populateTable(data);
                        epochs.synchronizeSelections();
                        epochs.setClickEvents();
                        epochs.onDoubleClick(function() { showDialog(epochs_popup, { epoch_id: getId(this.id) }); });

                        refreshDatasets(
                        {
                            selected_rows: epochs.getSelectedRows()
                        });
                        toggleObject(table_body.closest('table'), true, null);
                        epochs.stopLoading();
                    }
                    else
                    {
                        alert('Failed'); // implement better alert
                    }
                },
            }); // ajax call
        }
        else
        {
            toggleObject(datasets.getBody().closest('table'), false);
            toggleObject(table_body.closest('table'), false);
            epochs.stopLoading();
        }
    };

    var refreshDatasets = function(event)
    {
        datasets.startLoading();
        var epoch_row = event ? event.selected_rows : null;
        var table_body = datasets.getBody();
        if (epoch_row && epoch_row.length == 1) // make sure we didn't get passed an empty list
        {
            var epoch_id = getId(epoch_row.attr('id'))
            $.ajax(
            {
                type: 'POST',
                url: "browse/list_query",
                dataType: "json",
                data: { dataset_list: epoch_id },
                success: function(data)
                {
                    if (data.success)
                    {
                        datasets.populateTable(data);
                        datasets.synchronizeSelections();
                        datasets.setClickEvents();
                        datasets.onDoubleClick(function() { showDialog(datasets_popup, { dataset_id: getId(this.id) }); });
                        toggleObject(table_body.closest('table'), true);
                        datasets.stopLoading();
                    }
                    else
                    {
                        alert('Failed'); // implement better alert
                    }
                },
            }); // ajax call
        }
        else
        {
            toggleObject(table_body.closest('table'), false);
            datasets.stopLoading();
        }
    };

    var wireUpDrillDown = function()
    {
        document.onkeydown = function(e)
        {
            var k = e.keyCode;
            if (k >= 37 && k <= 40)
            {
                if (k == 38)
                {
                    ScrolltableManager.getFocus().changeRow(-1);
                }
                else if (k == 40)
                {
                    ScrolltableManager.getFocus().changeRow(1);
                }
                else if (k == 37 || k == 39)
                {
                    var current_focus = ScrolltableManager.getFocus().getElement().attr('id');
                    if ((current_focus == "experiments" && k == 39) || (current_focus == "epochs" && k == 37))
                    {
                        ScrolltableManager.setFocus("sessions");
                        sessions.changeRow(0);
                    }
                    else if ((current_focus == "sessions" && k == 39) || (current_focus == "datasets" && k == 37))
                    {
                        ScrolltableManager.setFocus("epochs");
                        epochs.changeRow(0);
                    }
                    else if (current_focus == "epochs" && k == 39)
                    {
                        ScrolltableManager.setFocus("datasets");
                        datasets.changeRow(0);
                    }
                    else if (current_focus == "sessions" && k == 37)
                    {
                        ScrolltableManager.setFocus("experiments");
                        experiments.changeRow(0);
                    }
                }
                return false;
            }
        }
    };

    var showDialog = function(popup, ajax_data)
    {
        console.log(ajax_data);
        $.ajax({
            traditional: true,
            type: 'POST',
            url: "browse/get_popup_data",
            dataType: "json",
            data: ajax_data,
            success: function(data)
            {
                if (data.success)
                {
                    // Do to all boxes
                    popup.find('p').text(data.name);
                    // Box specific modifications
                    switch (data.type)
                    {
                        case "experiment":
                            popup.attr('title', data.type + " " + ajax_data.exp_id);
                            break;
                        case "session":
                            popup.attr('title', data.type + " " + ajax_data.sess_id);
                            break;
                        case "epoch":
                            popup.attr('title', data.type + " " + ajax_data.epoch_id);
                            break;
                        case "dataset":
                            popup.attr('title', data.type + " " + ajax_data.dataset_id);
                            break;
                    }
                    popup.dialog({
                        resizable:false,
                        modal:true,
                        buttons: {
                            Okay: function() {
                                $(this).dialog("close");
                            },
                            Cancel: function() {
                                $(this).dialog("close");
                            }
                        },
                    });
                }
            },
        });
    };

// TODO - separate functions for each popup - handle custom populating the divs
// that represent the popups. showdialog will be one core function for popping
// up the dialog, and perhaps ill rename the other functions so it's not too
// confusing
    var init = function()
    {
        wireUpDrillDown();
        ScrolltableManager.init();
        ScrolltableManager.setTableHeights();
        ScrolltableManager.autoSetTableHeights();

        experiments = ScrolltableManager.getById("experiments");
        sessions = ScrolltableManager.getById("sessions");
        epochs = ScrolltableManager.getById("epochs");
        datasets = ScrolltableManager.getById("datasets");

        experiments.onSelect(refreshSessions);
        sessions.onSelect(refreshEpochs);
        epochs.onSelect(refreshDatasets);

        refreshExperiments();

        var sessions_table = $("#sessions .scrolltable_body table");
        var experiments_table = $("#experiments .scrolltable_body table");
        var epochs_table = $("#epochs .scrolltable_body table");
        var datasets_table = $("#datasets .scrolltable_body table");

        TableDragAndDrop.setupDraggable(sessions_table);
        TableDragAndDrop.setupDraggable(experiments_table);
        TableDragAndDrop.setupDraggable(epochs_table);
        TableDragAndDrop.setupDraggable(datasets_table);
        TableDragAndDrop.setupDroppable("#sessions .scrolltable_body table", sessions_table, $("#download_drop"), dropDownloads);
        TableDragAndDrop.setupDroppable(".scrolltable_body table", $("#trash_drop"), dropTrash);

        $("#radio_trash input").change(changeTrashFlag);
        $($("#radio_trash input")[getTrashFlag()]).click();

        $(".pop").dialog();
        $(".pop").dialog("destroy");

        experiments_popup = $("#experiments_pop");
        sessions_popup = $("#sessions_pop");
        epochs_popup = $("#epochs_pop");
        datasets_popup = $("#datasets_pop");
    };

    $(function() {
        init();
    });
});
