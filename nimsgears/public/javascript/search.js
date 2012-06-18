require(['utility/scrolltab/drilldown', 'utility/scrolltab/manager', 'dialog'], function (Drilldown, DrilldownManager, Dialog) {
    var epochs_popup;
    var datasets_popup;

    var getId = function(string)
    {
        return string.split("_")[1];
    };

    var refreshEpochs = function(table, selected_rows, is_instant, populateNextTableFn)
    {
        $.ajax(
        {
            type: 'POST',
            url: "post_search",
            dataType: "json",
            data: $("#search_form").serialize(),
            success: function(data)
            {
                if (data.success)
                {
                    populateNextTableFn(table, data);
                    table.synchronizeSelections();
                    epochs.onDoubleClick(function() { Dialog.showDialog(epochs_popup, { epoch_id: getId(this.id) }, "browse/get_popup_data"); });
                }
                else
                {
                    alert('Failed'); // implement better alert
                }
                table.select(is_instant);
            },
        }); // ajax call
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
                        datasets.onDoubleClick(function() { Dialog.showDialog(datasets_popup, { dataset_id: getId(this.id) }, "browse/get_popup_data"); });
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
    }

    var init = function()
    {
        epochs_popup = $("#epochs_pop");
        datasets_popup = $("#datasets_pop");

        epochs = new Drilldown("epochs", "Results");
        datasets = new Drilldown("datasets", "Datasets");
        manager = new DrilldownManager([epochs, datasets], [refreshEpochs, refreshDatasets], true);

        $("#search_form").submit(function()
        {
            manager.refresh(0, [], false);
            return false;
        });
    }

    $(function() {
        init();
    });
});
