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
        // $('#bannerpy').addClass('hide');
        
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
                    //window.alert("algo ha fallado / parametros incorrectos / ... ");
                    
                    data.data = [];
                    populateNextTableFn(table, data);
                    // $('#bannerpy-content').text(data.error_message);
//                     $('#bannerpy').removeClass('hide');
                }
                table.select(is_instant);
            },
        }); // ajax call
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


    $(function() {
        $("#date_from").datepicker(
                {
                    defaultDate : "-1m",
                    changeMonth : true,
                    changeYear : true,
                    numberOfMonths : 2,
                    maxDate : "+1d",
                    onSelect : function(selectedDate) {
                        $("#date_to").datepicker("option",
                                "minDate", selectedDate);
                    }
                });
        $("#date_to").datepicker(
                {
                    defaultDate : "+0d",
                    changeMonth : true,
                    changeYear : true,
                    numberOfMonths : 2,
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




// Map of parameter options and functions to validate fields
var validation_inputs = {
    'Subject Name' : is_ascii,
    'Subject Age' : is_ascii,
    'Exam' : is_integer,
    'Operator' : is_ascii,
    'PSD Name' : is_ascii,
};


var error_ascii = [];
var error_int = [];

// Validation functions
function is_ascii(value){
   //var patt1=/^[a-zA-Z\s]*$/;
   var pattascii=/^[\x00-\x7F]*$/;
   if(!pattascii.test(value)){
       error_ascii.push(value);
       return false
   }
   return true;
}

function is_integer(value){
    if(value == '')
        return true
    var patt2=/^\d+$/;
    if(!patt2.test(value)){
        error_int.push(value);
        return false;
    }
    return true;
}

function is_otherfield(value){
    return true;
}

// Validation of the fields

$('#submit').click( function(){
    error_ascii = [];
    error_int = [];
	var validationError = false;

	$('.criteriaBody').each(function(){
        var optionA = $(this).children('#criteriaContainerA').find('.search_param').val();
        var optionB = $(this).children('#criteriaContainerB').find('.search_param').val();
        if (optionA != 'Scan Type'){
            var valueA = $(this).children('#criteriaContainerA').find('.required').val();
            validation_inputs[optionA](valueA);
        }
        if (optionB != 'Scan Type'){
            var valueB = $(this).children('#criteriaContainerB').find('.required').val();
            validation_inputs[optionB](valueB);
        }
        if(error_ascii.length != 0 ){
            $('#bannerjs-errorstring').html("Fields <b>" + error_ascii.toString() + "</b> is not ascii");
            $('#bannerjs-errorstring').removeClass('hide');
        }else{
            $('#bannerjs-errorstring').addClass('hide');
        }
        if(error_int.length != 0 ){
            $('#bannerjs-errorints').html("Fields <b>" + error_int.toString() + "</b> do not correspond to integer");
            $('#bannerjs-errorints').removeClass('hide');
        }else{
            $('#bannerjs-errorints').addClass('hide');
        }
	});      
	if( validationError ){
		return false;
	}
});


 //Show the First Name and Last Name only when search in your data:
 $('#data_checkBox').live('click', function(){ 
     if($('#data_checkBox').is(':checked')){
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
 
   
