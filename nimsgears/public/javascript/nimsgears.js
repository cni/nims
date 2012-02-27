var SORTED_DATA = "sorted_data";
var LAST_CLICKED_INDEX = "last_clicked_index";
var SHIFT_BOUNDARY_INDEX = "shift_boundary_index";

/*
 * SCROLLTABLE CONSTRUCTION
 */
function scrolltable_Compare(a, b)
{
    if (a < b) { return -1; }
    else if (a == b) { return 0; }
    else { return 1; }
};


// Resorts the elements based on the existing sorted order (in case you
// repopulated the table)
function scrolltable_Resort(scrolltable_wrapper)
{
    var sorted_column;
    var sorted_direction;
    var sorted_data = scrolltable_wrapper.data(SORTED_DATA);
    if (sorted_data != null)
    {
        sorted_column = sorted_data[0];
        sorted_direction = sorted_data[1];
        scrolltable_SortByColumnIndex(scrolltable_wrapper, sorted_column, sorted_direction);
    }
};

function scrolltable_SortByElement(th_element)
{
    var scrolltable_wrapper = th_element.closest('.scrolltable_wrapper');
    var columns = scrolltable_wrapper.find('thead th');
    var column_index = columns.index(th_element);

    var sorted_column;
    var sorted_data = scrolltable_wrapper.data(SORTED_DATA);
    var sorted_direction = 1; // ascending by default
    if (sorted_data != null)
    {
        sorted_column = sorted_data[0];
        sorted_direction = sorted_data[1];
    }
    sorted_direction = (sorted_column == column_index) ? (-sorted_direction) : 1;
    scrolltable_SortByColumnIndex(scrolltable_wrapper, column_index, sorted_direction);
};

function scrolltable_SortByColumnIndex(scrolltable_wrapper, column_index, direction)
{
    var rows = scrolltable_wrapper.find('.scrolltable_body tbody tr');

    // First operation determines order rows go in:
    // We actually do this backwards from the 'intended' order, and then put
    // them all in place backwards
    var cell_text_a;
    var cell_text_b;
    var sorted_rows = rows.sort(function(a, b)
    {
        cell_text_a = $(a).children()[column_index].textContent;
        cell_text_b = $(b).children()[column_index].textContent;
        return -direction * scrolltable_Compare(cell_text_a, cell_text_b);
    });

    // Second puts them in the proper order:
    // With them all sorted 'backwards', we go through all the items besides
    // the first, and stick them in front of each other.  By the end, we have
    // our list sorted.  I'm sure I had a reason...
    var index;
    var inserting_node;
    var fixed_node;
    sorted_rows.slice(1).each(function()
    {
        index = sorted_rows.index(this);
        var inserting_node = this;
        var fixed_node = sorted_rows[index - 1];
        this.parentNode.insertBefore(inserting_node, fixed_node);
    });

    scrolltable_wrapper.data(SORTED_DATA, [column_index, direction]);
    scrolltable_Stripe(scrolltable_wrapper);
};

function scrolltable_Stripe(scrolltable_wrapper)
{
    scrolltable_wrapper.find('.scrolltable_body tbody tr').removeClass('alternate');
    scrolltable_wrapper.find('.scrolltable_body tbody tr:odd').addClass('alternate');
};

function scrolltable_Generate()
{
    var table_clone_body;
    var table_clone_header;

    var scrolltable_body;
    var scrolltable_header;
    var scrolltable_wrapper;

    var scrolltables = $(".scrolltable");
    scrolltables.each(function()
    {
        scrolltable_body = document.createElement('div');
        scrolltable_header = document.createElement('div');
        scrolltable_wrapper = document.createElement('div');
        scrolltable_body.className = 'scrolltable_body';
        scrolltable_header.className = 'scrolltable_header';
        scrolltable_wrapper.className = 'scrolltable_wrapper';
        scrolltable_wrapper.appendChild(scrolltable_header);
        scrolltable_wrapper.appendChild(scrolltable_body);

        table_clone_body = $(this).clone();
        table_clone_header = table_clone_body.clone();

        scrolltable_wrapper.setAttribute('id', table_clone_body.attr('id'));

        table_clone_body.removeAttr('id');
        table_clone_header.removeAttr('id');

        // We do a few steps to clean up the header on the table we're putting
        // into the body. We intend to keep it, because as long as we have a
        // header we can use it to fix the column widths in the body of the
        // table.
        table_clone_body.find('thead th').each(function()
        {
            var el = $(this);
            // Clean out the content - we just need the cells
            el.children().remove();
            el.text('');
            // Set the class to hide header, and remove id to prevent
            // duplicates in the DOM
            el.addClass('scrolltable_flat');
            el.removeAttr('id');
        });

        // Fewer steps needed on the one for the header - the body is useless
        // so we just dump it
        table_clone_header.find('tbody').remove();

        scrolltable_body.appendChild(table_clone_body[0]);
        scrolltable_header.appendChild(table_clone_header[0]);

        this.parentNode.replaceChild(scrolltable_wrapper, this);

        // Sort first time we create table.  Also lazily instantiates
        // SORTED_DATA field on table.
        scrolltable_SortByColumnIndex($(scrolltable_wrapper), 0, 1);
        $(scrolltable_header).find('th').click(function()
        {
            scrolltable_SortByElement($(this));
        });
    });
}

/*
 ******************************************************************************
 */

/*
 * UTILITY
 */

function setupDroppable(source, target, onDrop)
{
    target.droppable({
        hoverClass: 'hover',
        tolerance: "pointer",
        drop: onDrop,
        accept: source.selector
    });
};

function setupDraggable(source) {
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

function createTableRow(text_tuple)
{
    var td;
    var tr = document.createElement('tr');
    var n_elements = text_tuple.length;
    for (var i = 0; i < n_elements; i++) {
        td = document.createElement('td');
        td.textContent = text_tuple[i];
        tr.appendChild(td);
    }
    return tr;
}

function viewport()
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
 ******************************************************************************
 */

/*
 * REFRESH/AJAX FUNCTIONS
 */

function refreshEpochList(session_row)
{
    var table_body;
    table_body = $("#epochs .scrolltable_body tbody");
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
                var row;
                table_body.children().remove();
                data.forEach(function(text_tuple)
                {
                    row = createTableRow(text_tuple.splice(1));
                    row.id = 'epoch_' + text_tuple[0];
                    table_body.append(row);
                });

                toggleObject(table_body.closest('table'), true);

                var epoch_rows = $("#epochs .scrolltable_body tbody tr");
                epoch_rows.mouseup(singleRowSelect);
                epoch_rows.mousedown(multiRowSelect);
                scrolltable_Resort($("#epochs"));
                setupDraggable($("#epochs .scrolltable_body"));
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
    var table_body = $("#sessions .scrolltable_body tbody");
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
                var experiment_rows = $("#experiments .scrolltable_body tbody tr");
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
                    $("#experiments .scrolltable_body tbody tr").droppable("option", "disabled", true);
                }

                refreshEpochList(null);
                table_body.children().remove();

                data.forEach(function(text_tuple)
                {
                    row = createTableRow(text_tuple.splice(1));
                    row.id = 'sess_' + text_tuple[0];
                    table_body.append(row);
                });

                var sessionRows = $("#sessions .scrolltable_body tbody tr");
                sessionRows.mouseup(singleRowSelect);
                sessionRows.mouseup(session_MouseUp);
                sessionRows.mousedown(multiRowSelect);
                sessionRows.mousedown(session_MouseDown);
                scrolltable_Resort($("#sessions"));
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

function refreshGroups(research_group)
{
    if (research_group)
    {
        $.ajax(
        {
            type: 'POST',
            url: "groups_query",
            dataType: "json",
            data:
            {
                research_group: research_group
            },
            success: function(data)
            {
                var body_selector = " .scrolltable_body tbody";
                var tables =
                {
                    'pis': $("#pis"),
                    'admins': $("#admins"),
                    'members': $("#members"),
                    'others': $("#others")
                };
                var cur_table;
                var cur_body;
                for (table in tables)
                {
                    if (tables.hasOwnProperty(table))
                    {
                        cur_table = tables[table];
                        cur_body = cur_table.find(body_selector);
                        cur_body.children().remove();
                        if (data.hasOwnProperty(table))
                        {
                            data[table].forEach(function(text_tuple)
                            {
                                cur_body.append(createTableRow(text_tuple));
                            });
                        }
                        scrolltable_Resort(cur_table);
                        var all_rows = $('.scrolltable_body tbody').find('tr');
                        all_rows.mouseup(singleRowSelect);
                        all_rows.mousedown(multiRowSelect);
                    }
                }
            },
        }); // ajax call
    }
};


/*
 ******************************************************************************
 */


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
        table.data(LAST_CLICKED_INDEX, indexClicked);
        table.data(SHIFT_BOUNDARY_INDEX, indexClicked);
        row_list.removeClass('ui-selected');
        row.addClass('ui-selected');
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

function session_MouseUp(event)
{
	if (!(event.shiftKey || event.metaKey))
    {
        refreshEpochList($(this));
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


function session_MouseDown(event)
{
	if (event.shiftKey || event.metaKey)
    {
        var table_body = $(this).closest('tbody');
        var selected_rows = table_body.find(".ui-selected");
        refreshEpochList(selected_rows.length != 1 ? null : selected_rows.first())
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
        var last = table.data(LAST_CLICKED_INDEX);
        var bound = table.data(SHIFT_BOUNDARY_INDEX);

        if (last != indexClicked)
        {
            setActivation(row_list, last, bound, false);
            setActivation(row_list, last, indexClicked, true);
            table.data(SHIFT_BOUNDARY_INDEX, indexClicked);
        }
	}
    else if (event.metaKey)
    {
        toggleActivation(row);
        if (row.hasClass('ui-selected'))
        {
            table.data(LAST_CLICKED_INDEX, indexClicked);
            table.data(SHIFT_BOUNDARY_INDEX, indexClicked);
        }
    }
};

function blurOnEnter(event)
{
    var chCode = ('charCode' in event) ? event.charCode : event.keyCode;
    if (chCode == 13) {
        $(this).blur();
    };
};

function dropSessionsOnExperiment(event, ui)
{
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
                    $("#sessions .scrolltable_body tbody tr").removeClass('alternate');
                    $("#sessions .scrolltable_body tbody tr:odd").addClass('alternate');
                }
                else
                {
                    alert("Transfer failed to commit.");
                }
        },
    });
}

function getIdDictionary(selected_rows)
{
    var id_dict = {};
    selected_rows.each(function()
    {
        var chunks = this.id.split('_');
        var key = chunks[0];
        if (id_dict[key] == null)
        {
            id_dict[key] = new Array();
        }
        id_dict[key].push(chunks[1]);
    });
    return id_dict;
};

function dropTrash(event, ui)
{
    var selected_rows;
    selected_rows = ui.helper.data('moving_rows');

    var id_dict = getIdDictionary(selected_rows);
    alert(id_dict);
    console.log(id_dict);
    /*
    $.ajax({
        traditional: true,
        type: 'POST',
        url: "trash",
        dataType: "json",
        data:
        {
            id_dict: id_dict
        },
    });
    */
};

function dropDownloads(event, ui)
{
    var selected_rows;
    selected_rows = ui.helper.data('moving_rows');

    var id_dict = getIdDictionary(selected_rows);
    console.log(id_dict);
    alert(id_dict);
    /*
    $.ajax({
        traditional: true,
        type: 'POST',
        url: "download",
        dataType: "json",
        data:
        {
            id_dict: id_dict
        },
    });
    */
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
            selected_rows.addClass('multihover');
        } else {
            selected_rows.removeClass('multihover');
        }
    });
    table_rows.bind("dropout", function (event, ui)
    {
        clearTimeout(ui.helper.data("timer"));
        if ($(this).hasClass('ui-selected'))
        {
            ui.helper.data("timer", setTimeout(function()
            {
                $(".multihover").removeClass('multihover');
            }, 100));
        }
    });
    table_rows.bind("drop", function (event, ui)
    {
        $(".multihover").removeClass('multihover');
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
    SetTableHeight();
    $(window).resize(function() { SetTableHeight(); });

    $("body").disableSelection();
    $("table.access").data(LAST_CLICKED_INDEX,0);
    $("table.access").data(SHIFT_BOUNDARY_INDEX,0);
    experiments_rows = $("#experiments .scrolltable_body tbody tr");
    experiments_rows.mouseup(singleRowSelect);
    experiments_rows.mousedown(multiRowSelect);
    users_rows = $("#users .scrolltable_body tbody tr");
    users_rows.mouseup(singleRowSelect);
    users_rows.mousedown(multiRowSelect);

    setupDraggable($("#users .scrolltable_body table"));
    setupDraggable($("#experiments .scrolltable_body table"));
    setupDroppable($("#users .scrolltable_body table"), $("#experiments .scrolltable_body tbody tr"), dropAccessModification);
    setupDroppable($("#experiments .scrolltable_body table"), $("#users .scrolltable_body tbody tr"), dropAccessModification);
    setupMultiDrop($("#users .scrolltable_body table"));
    setupMultiDrop($("#experiments .scrolltable_body table"));
};

function dropAccessModification(event, ui)
{
    var experiments_table = $("#experiments .scrolltable_body table");
    var users_table = $("#users .scrolltable_body table");
    var dropped_onto_row = $(this);
    var dropped_onto_table = dropped_onto_row.closest('table');
    var dragged_row = $(event.target).closest('tr');
    var modify_experiments;
    var modify_users;
    if (experiments_table.is(dropped_onto_table))
    {
        modify_users = dragged_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dragged_row;
        modify_experiments = dropped_onto_row.hasClass('ui-selected') ? experiments_table.find('.ui-selected') : dropped_onto_row;
    }
    else
    {
        modify_experiments = dragged_row.hasClass('ui-elected') ? experiments_table.find('.ui-selected') : dragged_row;
        modify_users = dropped_onto_row.hasClass('ui-selected') ? users_table.find('.ui-selected') : dropped_onto_row;
    }
    console.log(modify_experiments);
    console.log(modify_users);
};

function dropUsersOnGroup(event, ui)
{
    var dropped_onto_div = $(this);
    var dragged_row = $(event.target).closest('tr');
    var dragged_from_table = dragged_row.closest('table');
    var user_rows;
    var user_ids = new Array();
    var update_group_to = dropped_onto_div.closest('.scrolltable_wrapper').attr('id');

    user_rows = dragged_row.hasClass('ui-selected') ? dragged_from_table.find('.ui-selected') : dragged_row;
    user_rows.each(function()
    {
        user_ids.push(this.children[0].textContent);
        // TODO do this with an id on the rows instead of just using first TD -
        // probably more robust
    });

    console.log(user_ids);
    console.log(update_group_to);
};

function SetTableHeight()
{
    var vp_size = viewport();
    var table_height = vp_size.height - 320;
    table_height = table_height > 200 ? table_height : 200;
    $(".scrolltable_body").height(table_height);
};

function setupCallbacks_Groups()
{
    SetTableHeight();
    $(window).resize(function() { SetTableHeight(); });
    $("body").disableSelection();
    $("table.scrolltable").data(LAST_CLICKED_INDEX,0);
    $("table.scrolltable").data(SHIFT_BOUNDARY_INDEX,0);
    var all_tables = $(".scrolltable_body table");
    var all_rows = all_tables.find('tr');
    all_rows.mouseup(singleRowSelect);
    all_rows.mousedown(multiRowSelect);

    setupDraggable(all_tables);
    setupDroppable(all_tables, $(".scrolltable_body"), dropUsersOnGroup);
    // TODO set it up so you can't drop it on the source table
};

function setupCallbacks()
{
    SetTableHeight();
    $(window).resize(function() { SetTableHeight(); });
    $("body").disableSelection();
    $("table.scrolltable").data(LAST_CLICKED_INDEX,0);
    $("table.scrolltable").data(SHIFT_BOUNDARY_INDEX,0);
    var sessions_table = $("#sessions .scrolltable_body table");
    var experiments_table = $("#experiments .scrolltable_body table");
    var epochs_table = $("#epochs .scrolltable_body table");
    var experiments_rows = experiments_table.find('tr');
    experiments_rows.mouseup(singleRowSelect);
    experiments_rows.mouseup(experiment_MouseUp);
    experiments_rows.mousedown(multiRowSelect);
    experiments_rows.mousedown(experiment_MouseDown);

    setupDraggable(sessions_table);
    setupDraggable(experiments_table);
    setupDraggable(epochs_table);
    setupDroppable(sessions_table, $("#download_drop"), dropDownloads);
    setupDroppable($(".scrolltable_body table"), $("#trash_drop"), dropTrash);
    setupDroppable(sessions_table, experiments_rows, dropSessionsOnExperiment);

    //$("th").click(function() { scrolltable_Resort($(this), 1);});
};
