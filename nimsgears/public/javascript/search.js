//Author Sara Benito Arce

require(['utility/scrolltab/drilldown', 'utility/scrolltab/manager', 'utility/dialog'], function (Drilldown, DrilldownManager, Dialog) {
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

    var init = function()
    {
        epochs_popup = $("#epochs_pop");
        datasets_popup = $("#datasets_pop");
        Dialog.bindSizeChange(epochs_popup);
        Dialog.bindSizeChange(datasets_popup, 'dataset');

        epochs = new Drilldown("epochs", "Results", 2, -1);
        datasets = new Drilldown("datasets", "Datasets");
        manager = new DrilldownManager([epochs, datasets], [refreshEpochs, refreshDatasets], true);

        $("#search_form").submit(function()
        {
            manager.refresh(0, [], false);
            return false;
        });
    }

    $(document).ready(function() { init(); });
});


var error_ascii = [];
var error_int = [];

var validation_inputs = {
    'Subject Name' : is_ascii,
    'Subject Age' : is_ascii,
    'Exam' : is_integer,
    'Operator' : is_ascii,
    'PSD Name' : is_ascii,
};

// Validation functions
function is_ascii(value){
   value = value.trim();
   var pattascii=/^[/\s\.\-/0-9a-zA-Z]*$/;
   if(!pattascii.test(value)){
       error_ascii.push(value);
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
        error_int.push(value);

        return false;
    }
    return true;
}

// Validation of the fields
$('#submit').click(function(){
   error_ascii = [];
   error_int = [];
   var validationError = false;

   $('.required').each(function(){
       var name = $(this).parent().attr('value');
       var value = $(this).val();

       if (name == 'Exam') {
           if (!is_integer(value)) {
               validationError = true;
           }
       } else {
           if (!is_ascii(value)) {
               validationError = true;
           }
       }
       if(error_ascii.length != 0 ){
           $('#bannerjs-errorstring').html("Fields <b>" + error_ascii.toString() + "</b> is not ascii");
           $('#bannerjs-errorstring').removeClass('hide');
           validationError = true;
       }else{
           $('#bannerjs-errorstring').addClass('hide');
       }
       if(error_int.length != 0 ){
            $('#bannerjs-errorints').html("Fields <b>" + error_int.toString() + "</b> do not correspond to integer");
            $('#bannerjs-errorints').removeClass('hide');
            validationError = true;
        }else{
            $('#bannerjs-errorints').addClass('hide');
        }
   });

   if (validationError) {
       return false;
    }
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

 //Set First Name and Last Name visible after clear search_all
 $('#clear_values').live('click', function(){
     if($('#data_checkBox').is(':checked')){
         $('#restricted_datasets').show();
         $('#first_name, #last_name').removeAttr('disabled');
         $('.first_name, .last_name').css('color', '#000000 ');
         $('#first_name, #last_name').css('color', '#000000 ');
         $('#bannerjs-errorints').addClass('hide');
         $('#bannerjs-errorstring').addClass('hide');
         $('#bannerpy').addClass('hide');
     }
 });

 //If superUser, then by default all dataset checkbox is checked
 if ($('#flagIsSuperUser').text() == 'True'){
     $('#data_checkBox').attr('checked', 'checked');
 }else{
     $('#data_checkBox').removeAttr('checked');
 }