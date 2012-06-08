require(['./utility/tablednd', './utility/scrolltab_mgr', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, ScrolltableManager, Drilldown, DrilldownManager) {
    var experiments;
    var sessions;
    var epochs;
    var datasets;

    var manager;

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
                    manager.refresh(0);
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
                            manager.refresh(3);
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
                    manager.refresh(0);
                }
                else
                {
                    alert('Failed');
                }
            },
        });
    };

    var refreshExperiments = function(table, selected_rows, populateNextTableFn)
    {
        //var table_body = experiments.getBody();
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
                    //experiments.populateTable(data);
                    //experiments.synchronizeSelections();
                    //experiments.setClickEvents();
                    //experiments.onDoubleClick(function() { showDialog(experiments_popup, { exp_id: getId(this.id) }); });
                    TableDragAndDrop.setupDroppable(sessions._getBodyTable(), $(experiments.getRows()), dropSessionsOnExperiment);
                    //refreshSessions(
                    //{
                    //    selected_rows: experiments.getSelectedRows()
                    //});
                    //experiments.stopLoading();
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
            },
        }); // ajax call
        table.select();
    };
    var refreshSessions = function(table, selected_rows, populateNextTableFn)
    {
        if (selected_rows && selected_rows.length == 1) // make sure we didn't just get passed an empty list
        {
            var exp_id = getId(selected_rows[0].id);
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
                        populateNextTableFn(table, data);
                        //sessions.onDoubleClick(function() { showDialog(sessions_popup, { sess_id: getId(this.id) }); });

                        //// Disable rows that you don't have manage access to
                        //var experiment_rows = experiments.getRows();
                        //if (experiment_row.hasClass('access_mg'))
                        //{
                        //    experiment_rows.each(function()
                        //    {
                        //        var disable_drop = !$(this).hasClass('access_mg') || $(this).is(experiment_row);
                        //        $(this).droppable("option", "disabled", disable_drop);
                        //    });
                        //}
                        //else
                        //{
                        //    experiment_rows.droppable("option", "disabled", true);
                        //}
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
            populateNextTableFn(table, []);
        }
        table.select();
    };

    var refreshEpochs = function(table, selected_rows, populateNextTableFn)
    {
        if (selected_rows && selected_rows.length == 1) // make sure we didn't get passed an empty list
        {
            var sess_id = getId(selected_rows[0].id);
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
                        populateNextTableFn(table, data);
                        //epochs.onDoubleClick(function() { showDialog(epochs_popup, { epoch_id: getId(this.id) }); });
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
            populateNextTableFn(table, []);
        }
        table.select();
    };

    var refreshDatasets = function(table, selected_rows, populateNextTableFn)
    {
        if (selected_rows && selected_rows.length == 1) // make sure we didn't get passed an empty list
        {
            var epoch_id = getId(selected_rows[0].id);
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
                        populateNextTableFn(table, data);
                        //datasets.onDoubleClick(function() { showDialog(datasets_popup, { dataset_id: getId(this.id) }); });
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
            populateNextTableFn(table, []);
        }
        table.select();
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
        experiments = new Drilldown("experiments", "Experiments");
        sessions = new Drilldown("sessions", "Sessions");
        epochs = new Drilldown("epochs", "Epochs");
        datasets = new Drilldown("datasets", "Datasets");
        manager = new DrilldownManager([experiments, sessions, epochs, datasets], [refreshExperiments, refreshSessions, refreshEpochs, refreshDatasets]);
        manager.refresh(0);

        TableDragAndDrop.setupDraggable($(experiments._getBodyTable()));
        TableDragAndDrop.setupDraggable($(sessions._getBodyTable()));
        TableDragAndDrop.setupDraggable($(epochs._getBodyTable()));
        TableDragAndDrop.setupDraggable($(datasets._getBodyTable()));
        TableDragAndDrop.setupDroppable("#sessions .scrolltable_body table", $("#download_drop"), dropDownloads);
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
