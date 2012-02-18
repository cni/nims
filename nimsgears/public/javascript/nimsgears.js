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
        $(this).removeClass('ui-state-disabled');
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

function makeSessionRow(session_tuple)
{
    var session_row = document.createElement('tr');
    var session_cell;
    session_row.id = 'sess_' + session_tuple[0];
    var n_session_tuples = session_tuple.length;
    for (var i = 1; i < n_session_tuples.length; i++)
    {
        session_cell = document.createElement('td');
        session_cell.textContent = session_tuple[i];
        session_row.appendChild(session_cell);
    }
    return session_row;
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
    var index_of_column = element.closest('thead').find('th').index(element);
    var rows = element.closest('table').find('tbody tr');
    var sorted_rows = rows.sort(function mysort(a, b) {
        return -direction * compare($($(a).find('td')[index_of_column]).text(), $($(b).find('td')[index_of_column]).text()); });
    sorted_rows.slice(1).each(function() {
        this.parentNode.insertBefore(this, sorted_rows[sorted_rows.index(this) - 1]); });
    sorted_rows.removeClass('alternate');
    sorted_rows.closest("tbody").find("tr:odd").addClass('alternate');
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
        revert: 'invalid',
        start: function(event, ui)
        {
            if (event.target.tagName != 'TD')
            {
                return false;
            }
        },
        stop: function(event, ui)
        {
            $(event.target).closest('table').data('moving_rows').css('visibility', 'visible');
        },
        helper: function(event, ui)
        {
            var moving_rows;
            var original_table = $(this);
            var clicked_row = $(event.target).closest("tr");
            var cloned_table = original_table.clone();
            cloned_table.width(source.width());
            if (clicked_row.hasClass('ui-selected'))
            {
                moving_rows = original_table.find('tr.ui-selected');
                cloned_table.find("tr:not(.ui-selected)").css("visibility","hidden");
            }
            else
            {
                moving_rows = clicked_row;
                var cloned_rows = cloned_table.find("tr");
                var clicked_row_ind = original_table.find("tr").index(clicked_row);
                cloned_rows.css("visibility","hidden");
                $(cloned_rows[clicked_row_ind]).css("visibility","visible");
            }
            if (event.target.tagName == 'TD')
            {
                moving_rows.css('visibility', 'hidden');
            }
            cloned_table.data('moving_rows', moving_rows);
            cloned_table.attr('id', 'floating');
            return cloned_table;
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
    var selected_rows;
    selected_rows = ui.helper.data('moving_rows');

    var sess_id_list = Array();
    selected_rows.each(function() { sess_id_list.push(this.id.split('_')[1]); });
    var target_exp_id = this.id.split("_")[1];
    $.ajax({
        traditional: true,
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
                    $("#sessions tbody tr").removeClass('alternate');
                    $("#sessions tbody tr:odd").addClass('alternate');
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
        epochCell.textContent = epochTuple[i];
        epochRow.appendChild(epochCell);
    }
    return epochRow;
};

function refreshEpochList(session_row)
{
    var table_body;
    table_body = $("#epochs tbody");
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
                var epoch_pusher = $("#epoch_container .pusher");
                epoch_pusher.height(session_row.position().top - epoch_pusher.position().top - 3); // - 3  for god knows why... need to figure this out TODO
                table_body.children().remove();
                for (var i = 0; i < data.length; i++)
                {
                    table_body.append(makeEpochRow(data[i]));
                }
                sortTable($("#epochs thead th").first(), 1);
                toggleObject(table_body.closest('table'), true);
            },
        }); // ajax call
    }
    else
    {
        toggleObject(table_body.closest('table'), false);
        table_body.children().remove();
    }
};

function refreshSessionList(experiment_row)
{
    var table_body = $("#sessions tbody");
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
                var experiment_rows = $("#experiments tbody tr");
                if (experiment_row.hasClass('access_mg'))
                {
                    experiment_rows.each(function()
                    {
                        if (!$(this).hasClass('access_mg') || $(this).is(experiment_row))
                        {
                            $(this).droppable("option", "disabled", true);
                        }
                        else
                        {
                            $(this).droppable("option", 'disabled', false);
                        }
                    });
                }
                else
                {
                    $("#experiments tbody tr").droppable("option", "disabled", true);
                }

                var sess_pusher = $("#sess_container .pusher");
                sess_pusher.height(experiment_row.position().top - sess_pusher.position().top - 3); // - 3  for god knows why... need to figure this out TODO
                refreshEpochList(null);
                table_body.children().remove();
                for (var i = 0; i < data.length; i++) // repopulate session table
                {
                    table_body.append(makeSessionRow(data[i]));
                }

                var sessionRows = $("#sessions tbody tr");
                setupDraggable($("#sessions"), $("#experiments tbody tr"));
                sessionRows.mouseup(singleRowSelect);
                sessionRows.mouseup(session_MouseUp);
                sessionRows.mousedown(multiRowSelect);
                sessionRows.mousedown(session_MouseDown);
                sortTable($("#sessions thead th").first(), 1);
                toggleObject(table_body.closest('table'), true);
            },
        });
    }
    else
    {
        refreshEpochList(null);
        toggleObject(table_body.closest('table'), false);
        table_body.children().remove(); // clean up session table
    }
};

function setupMultiDrop(table)
{
    var table_rows = table.find("tbody tr");
    table_rows.bind("dropover", function (event, ui)
    {
        var hovered_row = $(this);
        var table = hovered_row.closest("table");
        var selected_rows = table.find('.ui-selected');
        clearTimeout(ui.helper.data("timer"));
        if (hovered_row.hasClass('ui-selected'))
        {
            selected_rows.addClass('multiDragHover');
        } else {
            selected_rows.removeClass('multiDragHover');
        }
    });
    table_rows.bind("dropout", function (event, ui)
    {
        clearTimeout(ui.helper.data("timer"));
        if ($(this).hasClass('ui-selected'))
        {
            ui.helper.data("timer", setTimeout(function()
            {
                $(".multiDragHover").removeClass('multiDragHover');
            }, 100));
        }
    });
    table_rows.bind("drop", function (event, ui)
    {
        $(".multiDragHover").removeClass('multiDragHover');
    });
}

function toggleObject(object, makeVisible)
{
    objectVisible = object.css('display') != 'none';
    if ((makeVisible & !objectVisible) || (!makeVisible & objectVisible))
    {
        object.toggle('slide');
    }
};

function setupCallbacks_Access()
{
    $("body").disableSelection();
    sortTable($("#users thead th").first(), 1);
    sortTable($("#experiments thead th").first(), 1);
    $("table.access").data(lastClickedIndex,0);
    $("table.access").data(shiftBoundaryIndex,0);
    experiments_rows = $("#experiments tbody tr");
    experiments_rows.mouseup(singleRowSelect);
    experiments_rows.mousedown(multiRowSelect);
    users_rows = $("#users tbody tr");
    users_rows.mouseup(singleRowSelect);
    users_rows.mousedown(multiRowSelect);

    setupDraggable($("#users"), $("#experiments tbody tr"));
    setupDroppable($("#users"), $("#experiments tbody tr"), dropAccessModification);
    setupDraggable($("#experiments"), $("#users tbody tr"));
    setupDroppable($("#experiments"), $("#users tbody tr"), dropAccessModification);
    setupMultiDrop($("#users"));
    setupMultiDrop($("#experiments"));
};

function dropAccessModification(event, ui)
{
    var experiments = $("#experiments");
    var users = $("#users");
    var dropped_onto_table = $(this).closest('table');
    var dropped_onto_row = $(this);
    var dragged_row = $(event.target).closest('tr');
    var modify_experiments;
    var modify_users;
    if (experiments.is(dropped_onto_table))
    {
        modify_users = dragged_row.hasClass('ui-selected') ? users.find('.ui-selected') : dragged_row;
        modify_experiments = dropped_onto_row.hasClass('ui-selected') ? experiments.find('.ui-selected') : dropped_onto_row;
    }
    else
    {
        modify_experiments = dragged_row.hasClass('ui-elected') ? experiments.find('.ui-selected') : dragged_row;
        modify_users = dropped_onto_row.hasClass('ui-selected') ? users.find('.ui-selected') : dropped_onto_row;
    }
    console.log(modify_experiments);
    console.log(modify_users);
}

function setupCallbacks()
{
    $("body").disableSelection();
    sortTable($("#experiments thead th").first(), 1);
    $("table.manage").data(lastClickedIndex,0);
    $("table.manage").data(shiftBoundaryIndex,0);
    experiments_rows = $("#experiments tbody tr");
    experiments_rows.mouseup(singleRowSelect);
    experiments_rows.mouseup(experiment_MouseUp);
    experiments_rows.mousedown(multiRowSelect);
    experiments_rows.mousedown(experiment_MouseDown);
};
