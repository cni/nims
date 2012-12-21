require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager', 'utility/dialog'], function (TableDragAndDrop, Drilldown, DrilldownManager, Dialog) {
    var experiments;
    var sessions;
    var epochs;
    var datasets;

    var manager;

    var experiments_popup;
    var sessions_popup;
    var epochs_popup;
    var datasets_popup;

    /*
     * viewport
     * Helper function to return structure containing width and height of
     * viewable window.
     */
    var viewport = function ()
    {
        var e = window;
        a = 'inner';
        if ( !( 'innerWidth' in window ) )
        {
            a = 'client';
            e = document.documentElement || document.body;
        }
        return { width : e[ a+'Width' ] , height : e[ a+'Height' ] }
    }

    /*
     * getId
     * Given an id string, discard the specifier (exp, sess, etc) and return
     * the number itself. For example, id: "exp=200", returns "200".
     *
     * string - id pulled from a row
     */
    var getId = function(string)
    {
        return string.split("=")[1];
    };

    /*
     * toggleObject
     * Toggles the visibility of an object.
     *
     * object - object in question
     * makeVisible - true or false for visible or not visible, respectively
     */
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

    /*
     * getIdDictionary
     * Given a list of rows, returns a dictionary of types and a list of the
     * corresponding ids for each of those types. For example, given a list of
     * rows with ids ["exp=33", "sess=44", "exp=43"] it would return
     * {"exp":["33", "43"], "sess":["44"]}.
     *
     * selected_rows - rows you'd like to prune ids from
     */
    var getIdDictionary = function (selected_rows)
    {
        var id_dict = {};
        selected_rows.each(function()
        {
            var chunks = this.id.split('=');
            var key = chunks[0];
            if (id_dict[key] == null)
            {
                id_dict[key] = new Array();
            }
            id_dict[key].push(chunks[1]);
        });
        return id_dict;
    };

    /*
     * dropDownloads
     * Callback when a row or rows have been dropped on the downloads div.
     */
    var dropDownloads = function (event, ui)
    {
        var id_dict = getIdDictionary(ui.helper.data('moving_rows'));
        var iframe = document.getElementById("hidden_downloader");

        if (iframe === null)
        {
            iframe = document.createElement('iframe');
            iframe.id = "hidden_downloader";
            iframe.style.visibility = 'hidden';
            document.body.appendChild(iframe);
        }
        iframe.src = 'download?id_dict=' + JSON.stringify(id_dict)
    };

    /*
     * dropTrash
     * Callback when a row or rows have been dropped on the trash div.
     */
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
                    manager.refresh(0, [], true);
                }
                else
                {
                    alert('Failed');
                }
            },
        });
    };

    /*
     * dropSessionsOnExperiment
     * Callback when we've dropped a session or sessions onto another
     * experiment table row.
     */
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

    /*
     * getTrashFlag
     * Request and return the current trash flag from the server. Done
     * synchronously so that we can return the value.
     */
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

    /*
     * changeTrashFlag
     * Callback when a trash flag radio button has been selected. Refreshes
     * rows to reflect new table state.
     */
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
                    manager.refresh(0, [], true);
                }
                else
                {
                    alert('Failed');
                }
            },
        });
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
                    populateNextTableFn(table, data);
                    table.synchronizeSelections();
                    experiments.onDoubleClick(function()
                    {
                        Dialog.showDialog(experiments_popup, "experiment", "experiment/edit?id="+getId(this.id));
                        experiments_popup.on( "dialogbeforeclose", function( event, ui ) { manager.refresh(0, [], true); } );
                    });
                    TableDragAndDrop.setupDroppable(sessions._getBodyTable(), $(experiments.getRows()), dropSessionsOnExperiment);
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
     * refreshSessions
     * Populator for sessions table.
     *
     * table - session table
     * selected_rows - selected experiments rows to determine how to populate
     *      sessions
     * is_instant - whether refresh should happen immediately or wait for
     *      another request
     * populateNextTableFn - callback to populate the next table in the
     *      drilldown sequence (see drilldown manager)
     */
    var refreshSessions = function(table, selected_rows, is_instant, populateNextTableFn)
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
                        table.synchronizeSelections();
                        sessions.onDoubleClick(function()
                        {
                            Dialog.showDialog(sessions_popup, "session", "session/edit?id="+getId(this.id));
                            sessions_popup.on( "dialogbeforeclose", function( event, ui ) { manager.refresh(0, [], true); } );
                        });

                        //// Disable rows that you don't have manage access to
                        var experiment_rows = $(experiments.getRows());
                        experiment_row = $(selected_rows[0]);
                        if (experiment_row.hasClass('access_manage'))
                        {
                            experiment_rows.each(function()
                            {
                                var disable_drop = !$(this).hasClass('access_manage') || $(this).is(experiment_row);
                                $(this).droppable("option", "disabled", disable_drop);
                            });
                        }
                        else
                        {
                            experiment_rows.droppable("option", "disabled", true);
                        }
                    }
                    else
                    {
                        alert('Failed');
                    } // implement better alert TODO
                    table.select(is_instant);
                },
            });
        }
        else
        {
            populateNextTableFn(table, []);
            table.select(is_instant);
        }
    };

    /*
     * refreshEpochs
     * Populator for epochs table.
     *
     * table - epoch table
     * selected_rows - selected sessions rows to determine how to populate
     *      epochs
     * is_instant - whether refresh should happen immediately or wait for
     *      another request
     * populateNextTableFn - callback to populate the next table in the
     *      drilldown sequence (see drilldown manager)
     */
    var refreshEpochs = function(table, selected_rows, is_instant, populateNextTableFn)
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
                        table.synchronizeSelections();
                        epochs.onDoubleClick(function()
                        {
                            Dialog.showDialog(epochs_popup, "epoch", "epoch/edit?id="+getId(this.id));
                            epochs_popup.on( "dialogbeforeclose", function( event, ui ) { manager.refresh(0, [], true); } );
                        });
                    }
                    else
                    {
                        alert('Failed'); // implement better alert
                    }
                    table.select(is_instant);
                },
            }); // ajax call
        }
        else
        {
            populateNextTableFn(table, []);
            table.select(is_instant);
        }
    };

    /*
     * refreshDatasets
     * Populator for dataset table.
     *
     * table - dataset table
     * selected_rows - selected epochs rows to determine how to populate
     *      dataset
     * is_instant - whether refresh should happen immediately or wait for
     *      another request
     * populateNextTableFn - callback to populate the next table in the
     *      drilldown sequence (see drilldown manager)
     */
    var refreshDatasets = function(table, selected_rows, is_instant, populateNextTableFn)
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
                        table.synchronizeSelections();
                        datasets.onDoubleClick(function() { Dialog.showDialog(datasets_popup, "dataset", "dataset?id="+getId(this.id)); });
                    }
                    else
                    {
                        alert('Failed'); // implement better alert
                    }
                    table.select(is_instant);
                },
            }); // ajax call
        }
        else
        {
            populateNextTableFn(table, []);
            table.select(is_instant);
        }
    };

    var init = function()
    {
        experiments = new Drilldown("experiments", "Experiments");
        sessions = new Drilldown("sessions", "Sessions");
        epochs = new Drilldown("epochs", "Epochs");
        datasets = new Drilldown("datasets", "Datasets");
        manager = new DrilldownManager([experiments, sessions, epochs, datasets], [refreshExperiments, refreshSessions, refreshEpochs, refreshDatasets], true, "main");
        manager.refresh(0, [], true);

        TableDragAndDrop.setupDraggable($(experiments._getBodyTable()));
        TableDragAndDrop.setupDraggable($(sessions._getBodyTable()));
        TableDragAndDrop.setupDraggable($(epochs._getBodyTable()));
        TableDragAndDrop.setupDraggable($(datasets._getBodyTable()));
        TableDragAndDrop.setupDroppable("#sessions .scrolltable_body table, #datasets .scrolltable_body table", $("#download_drop"), dropDownloads);
        TableDragAndDrop.setupDroppable(".scrolltable_body table", $("#trash_drop"), dropTrash);

        $($("#radio_trash input")[getTrashFlag()]).click();
        $("#radio_trash input").change(changeTrashFlag);

        $(".pop").dialog();
        $(".pop").dialog("destroy");

        experiments_popup = $("#experiments_pop");
        Dialog.bindSizeChange(experiments_popup);
        sessions_popup = $("#sessions_pop");
        Dialog.bindSizeChange(sessions_popup);
        epochs_popup = $("#epochs_pop");
        Dialog.bindSizeChange(epochs_popup);
        datasets_popup = $("#datasets_pop");
        Dialog.bindSizeChange(datasets_popup, 'dataset');
    };

    $(document).ready(function() { init(); });
});
