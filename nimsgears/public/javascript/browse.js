require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager'], function (TableDragAndDrop, Drilldown, DrilldownManager) {
    var experiments;
    var sessions;
    var epochs;
    var datasets;

    var manager;

    var experiments_popup;
    var sessions_popup;
    var epochs_popup;
    var datasets_popup;

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

    var getId = function(string)
    {
        return string.split("=")[1];
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
                    manager.refresh(0, [], true);
                }
                else
                {
                    alert('Failed');
                }
            },
        });
    };

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
                    experiments.onDoubleClick(function() { showDialog(experiments_popup, "experiment", "/auth/experiment/edit?id="+getId(this.id)); });
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
                        sessions.onDoubleClick(function() { showDialog(sessions_popup, "session", "/auth/session/edit?id="+getId(this.id)); });

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
                        epochs.onDoubleClick(function() { showDialog(epochs_popup, "epoch", "/auth/epoch/edit?id="+getId(this.id)); });
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
                        datasets.onDoubleClick(function() { showDialog(datasets_popup, "dataset", "/auth/dataset?id="+getId(this.id)); });
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

    /* Render a jquery dialog for a given dialog (popup), type (string of
     * type), and load a particular URL into the dialog's iframe */
    var showDialog = function(popup, type, url)
    {
        var iframe = popup.find('iframe');
        // directs to the relevant URL
        iframe.attr('src', url);
        // then binds an event to show the popup when it is DONE loading
        iframe.bind('load.show', function() {
            // width and height of the iframe are computed and bound as minimum
            // width and height on the popup
            var width = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).width();
            var height = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).height();
            popup.dialog({
                beforeClose: function() { manager.refresh(0, [], true); },
                resizable:false,
                modal:true,
                closeOnEscape:true,
                minWidth:width,
                minHeight:height + 10
            });
            //popup.width(width);
            //popup.height(height);
            // unbind the show event (we don't want to reload the popup every
            // time it reloads, since we occasionally reload while the window
            // is still open
            iframe.unbind('load.show');
        });
        popup.attr('title', "Edit " + type);
    };

    /* Handles size adjustments when dialog boxes are reloaded while still
     * open. */
    var bindSizeChange = function(popup) {
        var iframe = popup.find('iframe');
        iframe.bind('load.sizechange', function() {
            var width = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).width();
            var height = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).height();
            iframe.width(width);
            iframe.height(height);
        });
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
        bindSizeChange(experiments_popup);
        sessions_popup = $("#sessions_pop");
        bindSizeChange(sessions_popup);
        epochs_popup = $("#epochs_pop");
        bindSizeChange(epochs_popup);
        datasets_popup = $("#datasets_pop");
        bindSizeChange(datasets_popup);
    };

    $(document).ready(function() { init(); });
});
