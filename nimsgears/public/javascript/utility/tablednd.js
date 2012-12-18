define([], function ()
{
    /*
     * setupDraggable
     * Enables row dragging on scrolltables.
     *
     * source - jquery scrolltable object to enable draggable rows on
     */
    var setupDraggable = function(source)
    {
        // A secondary table is created that floats with the cursor - this
        // table is given an id "floating" and has data attached to it in the
        // form of a jquery list object of all rows that are currently being
        // 'moved' in the table.
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
            // Creates table that follows drag motion - this creates the effect
            // of rows being dragged cleanly from their prior resting place
            helper: function(event, ui)
            {
                var moving_rows;
                var original_table = $(this);
                var clicked_row = $(event.target).closest("tr");
                var cloned_table = original_table.clone(); // cloned table = table that follows cursor

                // Ensure cloned table has identical width
                cloned_table.width(source.width());

                // Batch select if we've clicked an already selected row
                if (clicked_row.hasClass('ui-selected'))
                {
                    moving_rows = original_table.find('tr.ui-selected');
                    // Hide all unselected rows in the 'clone' table - they
                    // still take up space but are now hidden, making the
                    // dragging effect cleaner
                    cloned_table.find("tr:not(.ui-selected)").css("visibility","hidden");
                }
                // Otherwise, only drag the individual row we clicked on
                else
                {
                    moving_rows = clicked_row;
                    var cloned_rows = cloned_table.find("tr");
                    var clicked_row_ind = original_table.find("tr").index(clicked_row);

                    // Hide every row except the clicked row
                    cloned_rows.css("visibility","hidden");
                    $(cloned_rows[clicked_row_ind]).css("visibility","visible");
                }
                // Handles an edge case where we click between cells in a row
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

    /*
     * setupDroppable
     * Enables dropping on scrolltables.
     *
     * source - selector for draggable source(s)
     * target - jquery object for draggable target
     * onDrop - callback to fire on successful drop
     */
    var setupDroppable = function(source, target, onDrop)
    {
        target.droppable({
            hoverClass: 'hover',
            tolerance: "pointer",
            drop: onDrop,
            accept: source
        });
    };

    var init = function()
    {
        // I believe the purpose of this was to prevent the table from
        // stretching the page. Specifically, the cloned table that appears
        // when dragging a row occasionally is far longer than the page
        // content. Its appearance stretches the page, so we set the overflow
        // to hidden.
        document.getElementsByTagName("body")[0].style.overflow = "hidden";
    };

    return {
        init: init,
        setupDraggable: setupDraggable,
        setupDroppable: setupDroppable,
    };
});
