define([], function ()
{
    var setupDraggable = function(source)
    {
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

    var setupDroppable = function(source, target, onDrop)
    {
        target.droppable({
            hoverClass: 'hover',
            tolerance: "pointer",
            drop: onDrop,
            accept: source
        });
    };

    var setupMultiDrop = function(table)
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
    };

    var init = function()
    {

    };

    return {
        init: init,
        setupDraggable: setupDraggable,
        setupDroppable: setupDroppable,
        setupMultiDrop: setupMultiDrop,
    };
});
