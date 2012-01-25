    //Declaring variables to hold values that are used in multiple places.
    var epochTableName = 'sessions';
    var groupFilterName = 'groupFilter';
    var experimentFilterName = 'experimentFilter';
    var downloadTypeHeaderName = 'selectDownloadType_header';
    var downloadTypePrefix = '#selectDownloadType_';
    var groupColumn = 1;
    var experimentColumn = 2;
    var downloadOptionsColumn = 5;
    var allOption = '-all-'
    var searchTableName = "searchCondition";

    //Method that creates the table sorter control from the html table rendered in the page.
    function makeTablesorter(theTable, firstFilter, secondFilter)
    {
        var rowCount = document.getElementById(epochTableName).rows.length;
        if( rowCount > 1)
            $(theTable).tablesorter({ debug:false, sortList:[[0, 0]], widgets:['zebra'] })
                .tablesorterFilter({filterContainer: firstFilter, filterColumns: [groupColumn]},
		               {filterContainer: secondFilter, filterColumns: [experimentColumn]});
    };

    //Method that converts the select control in the table header and individual rows to DropDownCheckList.
    function createDropDownLists()
    {
        $('#'+downloadTypeHeaderName).dropdownchecklist();

        var rowCount = document.getElementById(epochTableName).rows.length;
        //Converting the select control in all individual records to a DropDownCheckList
        for(rowCounter = 1; rowCounter < rowCount; rowCounter++)
        {
            var dropDownId = document.getElementById(epochTableName).rows[rowCounter].cells[downloadOptionsColumn].childNodes[1].id.toString();
            $('#'+ dropDownId).dropdownchecklist();
        }
    }

    //Method that updates the individual select controls with download options in every row, based on selection in the header.
    //Whenever the header is updated, all the DropDownCheckLists in individual rows are overwritten based on selections in the header.
    function downloadOptionsHeaderSelectionChanged()
    {
        var rowCount = document.getElementById(epochTableName).rows.length;
        var headerOption = document.getElementById(downloadTypeHeaderName);
        var optionCount = headerOption.options.length;
        var selectedArray = new Array();

        //Find the list of download options from the DropDownCheckList present in the header of the table
        for(var headerOptionsCounter = 0; headerOptionsCounter<optionCount; headerOptionsCounter++)
            if(headerOption.options[headerOptionsCounter].selected)
                selectedArray.push(headerOption.options[headerOptionsCounter].value);

        //For each record in the table, update the selection of options corresponding to the selections made in the header.
        for(var rowCounter = 1; rowCounter <= rowCount; rowCounter ++)
        {
            dropDownInRow = document.getElementById(epochTableName).rows[rowCounter].cells[downloadOptionsColumn].childNodes[1]
            for(var optionCounter = 0; optionCounter < optionCount; optionCounter++)
            {
                currentOption = dropDownInRow.options[optionCounter];
                currentValue = currentOption.value;
                if(selectedArray.contains(currentValue))
                    currentOption.selected = true;
                else
                    currentOption.selected = false;
            }
            //Once the options have been updated, find the correct element and update the selections.
            $('#' + dropDownInRow.id).dropdownchecklist("updateSelection");
        }
    }

    //Method called when the selection in group filter changes. The experiment filter updates based on the groups selected.
    function groupChanged()
    {
        var groupFilter = document.getElementById(groupFilterName);
        var experimentFilter = document.getElementById(experimentFilterName);

        var selectedGroups = new Array();
        //Find the list of groups selected from the group filter.
        for (var iterator = 0; iterator < groupFilter.length; iterator++)
            if (groupFilter[iterator].selected)
                selectedGroups.push(groupFilter[iterator].value);

        //Removing all items other than '-all-'
        experimentFilter.options.length = 0;

        //If '-all-' is selected, set the value of selectedGroups to all the groups
        if(selectedGroups.contains(allOption))
            selectedGroups = groupExperimentMapping.Keys;

        experimentsToShow = new Array();
        //Find the list of experiments for each group selected from the filter.
        for (selectedGroupsIterator = 0; selectedGroupsIterator < selectedGroups.length; selectedGroupsIterator++)
        {
            currentGroup = selectedGroups[selectedGroupsIterator];
            experimentsToShow = experimentsToShow.concat(groupExperimentMapping.Lookup(currentGroup));
        }

        //Finding the unique list of experiments and sorting the list.
        experimentsToShow = experimentsToShow.getUnique();
        experimentsToShow.sort();

        experimentFilter.options[experimentFilter.length] = new Option(allOption, allOption);
        for (experimentIterator = 0; experimentIterator < experimentsToShow.length; experimentIterator++)
            experimentFilter.options[experimentFilter.length] = new Option(experimentsToShow[experimentIterator], experimentsToShow[experimentIterator]);

        //Setting '-all-' as the selected value.
        experimentFilter.selectedIndex = 0;
    }
    
    //Method called on clicking 'Add' button for searching the dataset.
    function addSearchClicked()
    {
        var table = document.getElementById(searchTableName);

        var rowCount = table.rows.length;
        var row = table.insertRow(rowCount);

        var cell0 = row.insertCell(0);
        var element0 = document.createElement("label");
        element0.innerHTML = "Search for:";
        cell0.appendChild(element0);

        var cell1 = row.insertCell(1);
        var element1 = document.createElement("input");
        cell1.appendChild(element1);

        var cell2 = row.insertCell(2);
        var element2 = document.createElement("select");

        //Variable to keep track whether the index for search by is selected so that we select an option that is not already selected.
        var indexForSearchBySelected = false;
        
        //Keep adding each option
        for (searchByIterator = 0; searchByIterator < searchOptions.length; searchByIterator++)
        {
            //Adding the current option
            element2.options[element2.length] = new Option(searchOptions[searchByIterator], searchOptions[searchByIterator]);

            if(!indexForSearchBySelected)
            {
                for(var i=0; i< table.rows.length - 1; i++)
                {
                    //If the option is not already selected, then select it as the index and set indexForSearchBySelected to 'true' so that we don't have to search for it anymore.
                    if(table.rows[i].cells[2].childNodes[0].value != searchOptions[searchByIterator])
                    {
                        element2.selectedIndex = searchByIterator;
                        indexForSearchBySelected = true;
                        break;
                    }
                }
            }
        }
        cell2.appendChild(element2);

        var cell3 = row.insertCell(3);
        var element3 = document.createElement("img");
        element3.src = "/images/remove.jpeg";
        element3.height = "15";
        element3.width = "15";
        element3.setAttribute('onclick', 'removeSearchClicked(this)'); 
        cell3.appendChild(element3);
        var element4 = document.createElement("img");
        element4.src = "/images/add.jpeg";
        element4.height = "15";
        element4.width = "15";
        element4.setAttribute('onclick', 'addSearchClicked()'); 
        cell3.appendChild(element4);
        
        //Hiding the 'Add' button from the previous row.
        //If there are more than one rows, the last row has both add and remove buttons
        if(table.rows.length <= 2)
            document.getElementById(searchTableName).rows[rowCount-1].cells[3].childNodes[0].style.display = 'none'
        else
            document.getElementById(searchTableName).rows[rowCount-1].cells[3].childNodes[1].style.display = 'none'
    }
    
    function removeSearchClicked(element)
    {
        var table = document.getElementById(searchTableName);
        var rowCount = table.rows.length;
 
        for(var i=0; i<rowCount; i++)
        {
            if(document.getElementById(searchTableName).rows[i].cells[3].childNodes[0] === element)
            {
                table.deleteRow(i);
                break;
            }
        }
        rowCount--;
        //Unhiding the 'Add' button in the last row.
        if(rowCount == 1)
            document.getElementById(searchTableName).rows[rowCount-1].cells[3].childNodes[0].style.display = ''
        else
            document.getElementById(searchTableName).rows[rowCount-1].cells[3].childNodes[1].style.display = ''
    }
    
    function searchRecords()
    {
        //alert(document.getElementById(searchTableName).rows[0].cells[0].childNodes[0].value);
        method = "post"; // Set method to post by default, if not specified.

        // The rest of this code assumes you are not using a library.
        // It can be made less wordy if you use one.
        var form = document.getElementById("queryform");

        searchTable = document.getElementById(searchTableName)
        var rowCount = searchTable.rows.length;
        
        var atLeastOneFilterSelected = false;
        for(var i=0; i<rowCount; i++)
        {
            if(searchTable.rows[i].cells[1].childNodes[0].value != '')
            {
                var hiddenField = document.createElement("input");
                hiddenField.setAttribute("type", "hidden");
                hiddenField.setAttribute("name", searchTable.rows[i].cells[2].childNodes[0].value);
                hiddenField.setAttribute("value", searchTable.rows[i].cells[1].childNodes[0].value);
                form.appendChild(hiddenField);
                atLeastOneFilterSelected = true;
            }
        }
        
        if (!atLeastOneFilterSelected)
        {
            var hiddenField = document.createElement("input");
            hiddenField.setAttribute("type", "hidden");
            hiddenField.setAttribute("name", searchTable.rows[0].cells[2].childNodes[0].value);
            hiddenField.setAttribute("value", "");
            form.appendChild(hiddenField);
        }

        document.body.appendChild(form);
        form.submit();
    }
