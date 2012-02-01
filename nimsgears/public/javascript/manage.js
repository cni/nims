var lastClickedIndex = "lastClickedIndex";
var shiftBoundaryIndex = "shiftBoundaryIndex";

function toggleActivation(a)
{
	if (a.hasClass('ui-selected')) {
		a.removeClass('ui-selected');
	} else {
		a.addClass('ui-selected');
	}
};

function setActivation(row_list, a, b, turnOn)
{
    var subset;
	if (a == b)
    {
		subset = $(row_list[a]);
	}
    else if (a < b)
    {
		subset = row_list.slice(a, b + 1);
	}
    else if (a > b)
    {
		subset = row_list.slice(b, a + 1);
	}

	if (turnOn)
    {
		subset.addClass('ui-selected');
	}
    else
    {
		subset.removeClass('ui-selected');
	}
};

function singleRowSelect(event)
{
	if (!(event.shiftKey || event.metaKey))
    {
        var row = $(this);
        var table = row.closest("table");
        var row_list = row.closest("tbody").find("tr");
        var indexClicked = row_list.index(row);
        table.data(lastClickedIndex, indexClicked);
        table.data(shiftBoundaryIndex, indexClicked);
        row_list.removeClass('ui-selected');
        row.addClass('ui-selected');
    }
};

function session_MouseUp(event)
{
	if (!(event.shiftKey || event.metaKey))
    {
        refreshEpochList($(this));
	}
};

function experiment_MouseUp(event)
{
	if (!(event.shiftKey || event.metaKey))
    {
        refreshSessionList($(this));
    }
};

function session_MouseDown(event)
{
	if (event.shiftKey || event.metaKey)
    {
        var table_body = $(this).closest('tbody');
        var selected_rows = table_body.find(".ui-selected");
        refreshEpochList(selected_rows.length != 1 ? null : selected_rows.first())
	}
};

function experiment_MouseDown(event)
{
    if (event.metaKey || event.shiftKey)
    {
        var table_body = $(this).closest('tbody');
        var selected_rows = table_body.find(".ui-selected");
        refreshSessionList(selected_rows.length != 1 ? null : selected_rows.first())
    }
};

function multiRowSelect(event)
{
    var row = $(this);
    var table = row.closest("table");
    var row_list = row.closest("tbody").find("tr");
    var indexClicked = row_list.index(row);
	if (event.shiftKey)
    {
        var last = table.data(lastClickedIndex);
        var bound = table.data(shiftBoundaryIndex);

        if (last != indexClicked)
        {
            setActivation(row_list, last, bound, false);
            setActivation(row_list, last, indexClicked, true);
            table.data(shiftBoundaryIndex, indexClicked);
        }
	}
    else if (event.metaKey)
    {
        toggleActivation(row);
        if (row.hasClass('ui-selected'))
        {
            table.data(lastClickedIndex, indexClicked);
            table.data(shiftBoundaryIndex, indexClicked);
        }
    }
};

function makeSessionRow(sessionTuple)
{
    var sessionRow = document.createElement('tr');
    var sessionCell;
    sessionRow.id = 'sess_' + sessionTuple[0];
    for (var i = 1; i < sessionTuple.length; i++)
    {
        sessionCell = document.createElement('td');
        sessionCell.textContent = sessionTuple[i];
        sessionRow.appendChild(sessionCell);
    }
    return sessionRow;
};

function compare(a, b) {
   if (a < b)
      return -1;
   else if (a == b)
      return 0;
   else
      return 1;
};

function sortTable(element, direction)
{
    var indexOfColumn = element.closest('thead').find('th').index(element);
    var rows = element.closest('table').find('tbody tr');
    var sorted_rows = rows.sort(function mysort(a, b) {
        return -direction * compare($($(a).find('td')[indexOfColumn]).text(), $($(b).find('td')[indexOfColumn]).text()); });
    sorted_rows.slice(1).each(function() {
        this.parentNode.insertBefore(this, sorted_rows[sorted_rows.index(this) - 1]); });
};

function blurOnEnter(event)
{
    var chCode = ('charCode' in event) ? event.charCode : event.keyCode;
    if (chCode == 13) {
        $(this).blur();
    };
};

function setupDraggable(source, target) {
    source.draggable({
        start: function(event, ui)
        {
            if (!$(event.target).closest("tr").hasClass('ui-selected'))
            {
                return false;
            }
            else
            {
                source.find(".ui-selected").css("visibility", "hidden");
            }

        },
        stop: function(event, ui)
        {
            source.find(".ui-selected").css("visibility", "visible");
        },
        helper: function()
        {
            var table = $("<table></table>").append($(this).clone()).width(source.width());
            table.find("tr:not(.ui-selected)").css("visibility","hidden");
            return table;
        },
        appendTo: 'body',
        opacity: 0.5,
    });
};

function setupDroppable(source, target, onDrop) {
    target.droppable({
        hoverClass: 'dragHover',
        tolerance: "pointer",
        drop: onDrop,
        accept: source.selector
    });
};

function dropSessionsOnExperiment(event, ui) {
    var selected_rows = $("#sessions tbody tr.ui-selected");
    var sess_id_list = Array();
    selected_rows.each(function() { sess_id_list.push(this.id.split('_')[1]); });
    var target_exp_id = this.id.split("_")[1];
    $.ajax({
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
                }
                else
                {
                    alert("Transfer failed to commit.");
                }
        },
    });
}

function makeEpochRow(epochTuple)
{
    var epochRow = document.createElement('tr');
    var epochCell;
    epochRow.id = 'epoch_' + epochTuple[0];
    for (var i = 1; i < epochTuple.length; i++) {
        epochCell = document.createElement('td');
        if (epoch_columns_flags[i-1] == 1) {
            var epochInput;
            epochInput = document.createElement('input');
            epochInput.value = epochTuple[i];
            // put this type of stuff into the CSS file eventually (with a class perhaps)
            epochInput.readOnly = true;
            epochInput.style.border = 'none';
            epochInput.style.background = 'transparent';
            epochInput.onkeypress = blurOnEnter;
            epochInput.onblur = function()
            {
                var inputObject = $(this);
                // verify they've changed the value since clicking it
                if (inputObject.val() != inputObject.data('cache')) {
                    epoch_id = inputObject.parents('tr').attr('id').split('_')[1];
                    inputObject.attr('readonly', true);
                    $.ajax({
                        type: 'POST',
                        url: "update_epoch",
                        dataType: "json",
                        data: {
                            id: epoch_id,
                            desc: inputObject.val()
                        },
                        success: function(data) {
                            if (!data.success) {
                                inputObject.val(inputObject.data('cache'));
                                alert("Change failed to commit.");
                            }
                        },
                    }); // ajax call
                }
            };
            epochCell.onclick = function()
            {
                input = $(this).children('input');
                input.data('cache', input.val());
                input.attr('readonly', false);
            };
            epochCell.appendChild(epochInput);
            }
            else
            {
              epochCell.textContent = epochTuple[i];
            }
        epochRow.appendChild(epochCell);
    }
    return epochRow;
};

function refreshEpochList(session_row)
{
    var table_body;
    var toggle;
    table_body = $("#epochs tbody");
    toggle = (table_body.closest('table').css('display') == 'none') ? true : false;
    if (session_row)
    {
        var sess_id = session_row.attr('id').split('_')[1];
        $.ajax(
        {
            type: 'POST',
            url: "epoch_query",
            dataType: "json",
            data:
            {
                id: sess_id
            },
            success: function(data)
            {
                table_body.children().remove();
                for (var i = 0; i < data.length; i++)
                {
                    table_body.append(makeEpochRow(data[i]));
                }

                if (toggle)
                {
                    table_body.closest('table').toggle('slide');
                }
            },
        }); // ajax call
    }
    else
    {
        table_body.children().remove();
        if (!toggle)
        {
            table_body.closest('table').toggle('slide');
        }
    }
};

function refreshSessionList(experiment_row)
{
    var table_body;
    if (experiment_row)
    {
        var exp_id = experiment_row.attr('id').split('_')[1];
        $.ajax(
        {
            type: 'POST',
            url: "session_query",
            dataType: "json",
            data: { id: exp_id },
            success: function(data)
            {
                refreshEpochList(null);
                table_body = refreshSessionList(null);
                for (var i = 0; i < data.length; i++) // repopulate session table
                {
                    table_body.append(makeSessionRow(data[i]));
                }
                setupDraggable($("#sessions tbody"), $("#experiments tbody tr"));
                $("#sessions tbody tr").mouseup(singleRowSelect);
                $("#sessions tbody tr").mouseup(session_MouseUp);
                $("#sessions tbody tr").mousedown(multiRowSelect);
                $("#sessions tbody tr").mousedown(session_MouseDown);
            },
        }); // ajax call
    }
    else
    {
        refreshEpochList(null);
        table_body = $("#sessions tbody");
        table_body.children().remove(); // clean up session table
    }
    return table_body
};

function setupCallbacks()
{
    $("table.manage").data(lastClickedIndex,0);
    $("table.manage").data(shiftBoundaryIndex,0);
    $("#experiments tbody tr").mouseup(singleRowSelect);
    $("#experiments tbody tr").mouseup(experiment_MouseUp);
    $("#experiments tbody tr").mousedown(multiRowSelect);
    $("#experiments tbody tr").mousedown(experiment_MouseDown);
};
