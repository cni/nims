var lastClickedIndex = "lastClickedIndex";
var shiftBoundaryIndex = "shiftBoundaryIndex";

function toggleActivation(a) {
	if (a.hasClass('ui-selected')) {
		a.removeClass('ui-selected');
	} else {
		a.addClass('ui-selected');
	}
};

function setActivation(row_list, a, b, turnOn)
{
	if (a == b) {
		subset = $(row_list[a]);
	} else if (a < b) {
		subset = row_list.slice(a, b + 1);
	} else if (a > b) {
		subset = row_list.slice(b, a + 1);
	}
	if (turnOn) {
		subset.addClass('ui-selected');
	} else {
		subset.removeClass('ui-selected');
	}
};

function singleRowSelect(event)
{
	if (!(event.shiftKey || event.metaKey)) {
        row = $(this);
        table = row.closest("table");
        row_list = row.closest("tbody").find("tr");
		indexClicked = row_list.index(row);
        table.data(lastClickedIndex, indexClicked);
        table.data(shiftBoundaryIndex, indexClicked);
		row_list.removeClass('ui-selected');
		row.addClass('ui-selected');
	}
};

function multiRowSelect(event)
{
    row = $(this);
	if (event.shiftKey) {
        table = row.closest("table");
        row_list = row.closest("tbody").find("tr");
		indexClicked = row_list.index(row);
        last = table.data(lastClickedIndex);
        bound = table.data(shiftBoundaryIndex);

		if (last != indexClicked) {
			setActivation(row_list, last, bound, false);
			setActivation(row_list, last, indexClicked, true);
			bound = indexClicked;
		}
	} else if (event.metaKey) {
		toggleActivation(row);
	}
};

function makeSessionRow(sessionTuple)
{
    var sessionRow = document.createElement('tr');
    var sessionCell;
    sessionRow.id = 'sess_' + sessionTuple[0];
    for (var i = 1; i < sessionTuple.length; i++) {
        sessionCell = document.createElement('td');
        sessionCell.textContent = sessionTuple[i];
        sessionRow.appendChild(sessionCell);
    }
    sessionCell = document.createElement('td');
    var span = document.createElement('span');
    span.className = 'sess_detail';
    span.textContent = ' >> ';
    sessionCell.appendChild(span);
    sessionRow.appendChild(sessionCell);
    return sessionRow;
};

function compare(a, b) {
   if (a < b)
      return -1;
   else if (a == b)
      return 0;
   else
      return 1;
}

function sortTable(element, direction) {
    indexOfColumn = element.closest('thead').find('th').index(element);
    rows = element.closest('table').find('tbody tr');
    sorted_rows = rows.sort(function mysort(a, b) {
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
        drag: function(event) {
            if (!$(this).hasClass('ui-selected')) { return false; }},
        helper: function(event) {
            return $('<div style="background-color:red";>FUCK YOU</div>');
        },
        appendTo: 'body',
    });
};

function setupDroppable(source, target) {
    target.droppable({
        hoverClass: 'bloop',
        drop: function(event, ui) {
            alert('row dropped ' + $(this).text());
        },
        accept: source.selector
    });
};

function makeEpochRow(epochTuple)
{
    var epochRow = document.createElement('tr');
    var epochCell;
    epochRow.id = 'epoch_' + epochTuple[0];
    for (var i = 1; i < epochTuple.length; i++) {
        epochCell = document.createElement('td');
        if (epoch_columns_flags[i-1] == 1) {
          epochInput = document.createElement('input');
          epochInput.value = epochTuple[i];
          // put this type of stuff into the CSS file eventually (with a class perhaps)
          epochInput.readOnly = true;
          epochInput.style.border = 'none';
          epochInput.style.background = 'transparent';
          epochInput.onkeypress = blurOnEnter;
          epochInput.onblur = function()
          {
            inputObject = $(this);
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
        } else {
          epochCell.textContent = epochTuple[i];
        }
        epochRow.appendChild(epochCell);
    }
    return epochRow;
};

function refreshEpochList()
{
    var sess_id = $(this).parents('tr').attr('id').split('_')[1];
    $.ajax({
        type: 'POST',
        url: "epoch_query",
        dataType: "json",
        data: {
            id: sess_id
        },
        success: function(data) {
            var table_body = $("#epochs tbody");
            table_body.children().remove();
            for (var i = 0; i < data.length; i++) {
                table_body.append(makeEpochRow(data[i]));
            }
        },
    }); // ajax call
};

function refreshSessionList()
{
    var exp_id = $(this).parents('tr').attr('id').split('_')[1];
    $.ajax({
        type: 'POST',
        url: "session_query",
        dataType: "json",
        data: {
            id: exp_id
        },
        success: function(data) {
            $("#epochs tbody").children().remove(); // clean up epoch table
            var table_body = $("#sessions tbody");
            table_body.children().remove(); // clean up session table
            for (var i = 0; i < data.length; i++) { // repopulate session table
                table_body.append(makeSessionRow(data[i]));
            }
            $(".sess_detail").click(refreshEpochList); // set callbacks on new expand buttons for epoch table
            setupDraggable($("#sessions tbody tr"), $("#t1 tr"));
            $("#sessions tbody tr").mouseup(singleRowSelect);
            $("#sessions tbody tr").mousedown(multiRowSelect);
        },
    }); // ajax call
};

function setupCallbacks()
{
    $("table.manage").data(lastClickedIndex,0);
    $("table.manage").data(shiftBoundaryIndex,0);
    $(".exp_detail").click(refreshSessionList);
};
