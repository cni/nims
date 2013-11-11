//Author Sara Benito Arce

require(['utility/tablednd', 'utility/scrolltab/drilldown', 'utility/scrolltab/manager', 'utility/dialog'], function (TableDragAndDrop, Drilldown, DrilldownManager, Dialog) {
    var epochs_popup;
    var datasets_popup;

    /*
     * getId
     * Given an id string, discard the specifier (exp, sess, etc) and return
     * the number itself. For example, id: "exp_200", returns "200".
     *
     * string - id pulled from a row
     */
    var getId = function(string)
    {
        return string.split("=")[1];
    };

    /*
     * refreshEpochs
     * Populator for epochs table.
     *
     * table - epoch table
     * selected_rows - not used (highest level table in drilldown)
     * is_instant - whether refresh should happen immediately or wait for
     *      another request
     * populateNextTableFn - callback to populate the next table in the
     *      drilldown sequence (see drilldown manager)
     */
    var refreshEpochs = function(table, selected_rows, is_instant, populateNextTableFn)
    {
        $.ajax(
        {
            type: 'POST',
            url: "search/query",
            dataType: "json",
            data: $("#search_form").serialize(),
            success: function(data)
            {
                if (data.success)
                {
                    if (data.data.length == 0) {
                        // Show "no results" error message
                        $('#bannerpy-content').html('Your search did not give any result');
                        $('#bannerpy').removeClass('hide');
                    } else {
                        $(".scrolltable_title:first").html( data.data.length + " Results");
                        $('#bannerpy').addClass('hide');
                    }
                    populateNextTableFn(table, data);
                    table.synchronizeSelections();
                    epochs.onDoubleClick(function() { Dialog.showDialog(epochs_popup, "epoch", "../epoch/edit?id="+getId(this.id)); });
                }
                else
                {
                    // Clear datasets list table and add error message
                    data.data = [];
                    populateNextTableFn(table, data);
                    if (data.error_message!='empty_fields'){
                        $('#bannerpy-content').text(data.error_message);
                        $('#bannerpy').removeClass('hide');
                    } else {
                        $('#bannerpy').addClass('hide');
                    }
                }
                table.select(is_instant);
            },
        });
    };

    /*
     * refreshDatasets
     * Populator for datasets table.
     *
     * table - dataset table
     * selected_rows - selected epochs rows to determine how to populate
     *      datasets
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
                        datasets.onDoubleClick(function() { Dialog.showDialog(datasets_popup, "dataset", "../dataset?id="+getId(this.id)); });
                    }
                    else
                    {
                        // Clear datasets list table and add error message
                        data.data = [];
                        populateNextTableFn(table, data);
                        $('#bannerpy-content').text('Error in getting datasets list');
                        $('#bannerpy').removeClass('hide');
                    }
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

    $(function() {
        $("#date_from").datepicker(
                {
                    defaultDate : "-1m",
                    dateFormat: 'yy-mm-dd',
                    changeMonth : true,
                    changeYear : true,
                    numberOfMonths : 1,
                    maxDate : "+1d",
                    onSelect : function(selectedDate) {
                        $("#date_to").datepicker("option",
                                "minDate", selectedDate);
                    }
                });
        $("#date_to").datepicker(
                {
                    defaultDate : "+0d",
                    dateFormat: 'yy-mm-dd',
                    changeMonth : true,
                    changeYear : true,
                    numberOfMonths : 1,
                    maxDate : "+1d",
                    onSelect : function(selectedDate) {
                        $("#date_from").datepicker(
                                "option", "maxDate",
                                selectedDate);
                    }
                });
    });

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
        console.log('id_dict: ', id_dict);
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
        iframe.src = '../download?&id_dict=' + JSON.stringify(id_dict)
        console.log('iframe.src: ', iframe.src);
        if ($('#download_drop input[id=raw]').is(':checked'))
            iframe.src += '&raw=1';
        if ($('#download_drop input[id=legacy]').is(':checked'))
            iframe.src += '&legacy=1';

    };

    var init = function()
    {
        epochs = new Drilldown("epochs", "Results", 2, -1);
        datasets = new Drilldown("datasets", "Datasets");
        manager = new DrilldownManager([epochs, datasets], [refreshEpochs, refreshDatasets], true);

        TableDragAndDrop.setupDraggable($(epochs._getBodyTable()));
        TableDragAndDrop.setupDraggable($(datasets._getBodyTable()));
        TableDragAndDrop.setupDroppable("#epochs .scrolltable_body table, #datasets .scrolltable_body table",
                                        $("#download_drop"), dropDownloads);

        epochs_popup = $("#epochs_pop");
        datasets_popup = $("#datasets_pop");
        Dialog.bindSizeChange(epochs_popup);
        Dialog.bindSizeChange(datasets_popup, 'dataset');

        $("#search_form").submit(function()
        {
            manager.refresh(0, [], false);
            return false;
        });
    }

    $(document).ready(function() { init(); });
});

// Validation functions
function is_ascii(value){
   value = value.trim();
   var pattascii=/^[/\s\.\-/0-9a-zA-Z]*$/;
   if(!pattascii.test(value)){
       return false;
   }
   return true;
}

function is_date(value){
    var pattern = /^(19|20|21)\d\d-(0[1-9]|1[012])-(0[1-9]|[12][0-9]|3[01])$/;
    if (value.length > 0 && !pattern.test(value)) {
        return false;
    }

    return true;
}

function is_integer(value){
    if(value == '')
        return true;
    value = value.trim();
    var patt2=/^\d+$/;
    if(!patt2.test(value)){
        return false;
    }
    return true;
}

// Validation of the fields
$('#submit').click(function(){
   var errors = [];
   var hasAtLeastOneParameter = false;

   $('.required').each(function(){
       var name = $(this).parent().attr('value');
       var value = $(this).val();

       if ($.inArray(name, ['Exam', 'Min Age', 'Max Age']) != -1) {
           if (!is_integer(value)) {
               errors.push('Field <b>' + name + '</b> needs to be an integer');
           }
       } else if (name == 'Date From' || name == 'Date To') {
           if (!is_date(value)) {
               errors.push('Field <b>' + name + '</b> needs to be a valid date');
           }
       } else if (!is_ascii(value)) {
           errors.push('Field <b>' + name + '</b>: "<b>' + value + '</b>" is not ascii');
       }

        if (value != '') {
            hasAtLeastOneParameter = true;
        }
   });

   if (errors.length > 0) {
       // There is validation error
       var errorsList = '';
       $.each(errors, function(idx, error) {
           errorsList += '<li>' + error + '</li>';
       });

       $('#bannerjs-errors').html('<ul>' + errorsList + '</ul>');
       $('#bannerjs-errors').removeClass('hide');
       return false;
   } else {
       $('#bannerjs-errors').addClass('hide');
   }

   var scan_type = $('#select_scan').val();
   var psd = $('#select_psd').val();

   //Show banner to advise there is no parameter in the query.
   if (!hasAtLeastOneParameter && scan_type=='' && psd=='') {
        $('#bannerjs-errors').html("This query has no parameters");
        $('#bannerjs-errors').removeClass('hide');
       return false;
   }

   return true;
});

 //Show the First Name and Last Name only when search in your data:
 $('#data_checkBox').live('click', function(){
     if($('#data_checkBox').is(':checked') && $('#flagIsSuperUser').text() != 'True'){
        $('#restricted_datasets').hide();
        $('#first_name, #last_name').attr('disabled', 'disabled');
        $('.first_name, .last_name').css('color', '#E0E0E0');
        $('#first_name, #last_name').css('color', '#E0E0E0');
    }else{
        $('#restricted_datasets').show();
        $('#first_name, #last_name').removeAttr('disabled');
        $('.first_name, .last_name').css('color', '#000000 ');
        $('#first_name, #last_name').css('color', '#000000 ');
    }
 });


 $('#clear_values').live('click', function(){
     //Set First Name and Last Name visible after clear search_all
     if($('#data_checkBox').is(':checked')){
         $('#restricted_datasets').show();
         $('#first_name, #last_name').removeAttr('disabled');
         $('.first_name, .last_name').css('color', '#000000 ');
         $('#first_name, #last_name').css('color', '#000000 ');
     }

     $('#bannerjs-errors').addClass('hide');
     $('#bannerpy').addClass('hide');
 });

 //If superUser, then by default all dataset checkbox is checked
 if ($('#flagIsSuperUser').text() == 'True'){
     $('#data_checkBox').attr('checked', 'checked');
 }else{
     $('#data_checkBox').removeAttr('checked');
 }