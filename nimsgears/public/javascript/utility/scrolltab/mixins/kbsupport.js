define(['./selectable'], function(asSelectable)
{
    return function()
    {
        asSelectable.call(this);

        /*
         * init_kbsupport
         */
        this.init_kbsupport = function()
        {
            this.auto_scroll_enabled = document.createElement("div").scrollIntoViewIfNeeded !== undefined;
            this.init_selectable();
            this.enableKeyboardSelection();
        };

        /*
         * changeRow
         * Accepts an integer specifying the direction to move row selection.
         * Used in conjunction with keypresses to navigate through rows in a
         * table. Returns true or false for whether or not the selection
         * succeeded.
         *
         * direction - integer -1, 0, or 1 to specify selecting the prior,
         *      same, or next row.
         */
        this.changeRow = function(direction)
        {
            var success = false;
            var rows = this.getRows();
            var change_to_index = this.last_clicked_index + direction;
            if ((change_to_index < rows.length) && (change_to_index >= 0))
            {
                var obj = this;
                this._selected_rows.forEach(function(row)
                {
                    obj._toggleSelect(row, false);
                });
                this._toggleSelect(rows[change_to_index], true);
                this.last_clicked_index = this.shift_clicked_index = change_to_index;
                if (this.auto_scroll_enabled)
                {
                    rows[change_to_index].scrollIntoViewIfNeeded(direction <= 0);
                }
                success = true;
            }
            return success;
        };

        /*
         * shiftRow
         * Comparable to changeRow, but in this case handles BATCH selection.
         * For example, if you hold shift and tap down, you would want to call
         * shiftRow(1) to shift select the next row. Returns true or false for
         * whether or not the selection succeeded.
         *
         * direction - integer -1, 0, or 1 to specify BATCH selecting the
         *      prior, same, or next row.
         */
        this.shiftRow = function(direction)
        {
            var success = false;
            var rows = this.getRows();
            var change_to_index = this.shift_clicked_index + direction;
            if ((change_to_index < rows.length) && (change_to_index >= 0))
            {
                this._batchSelect(rows, this.last_clicked_index, this.shift_clicked_index, false);
                this._batchSelect(rows, this.last_clicked_index, change_to_index, true);
                this.shift_clicked_index = change_to_index;
                if (this.auto_scroll_enabled)
                {
                    rows[change_to_index].scrollIntoViewIfNeeded(direction <= 0);
                }
                success = true;
            }
            return success;
        };

        /*
         * enableKeyboardSelection
         * Enables use of up and down keys to navigate up and down rows in the
         * table.
         */
        this.enableKeyboardSelection = function()
        {
            var obj = this;
            this.element.setAttribute("tabindex", 0);
            this.element.addEventListener("keydown", function(event)
            {
                var key = event.keyCode;
                if (key == 38)
                {
                    event.returnValue = false;
                    var success = event.shiftKey ? obj.shiftRow(-1) : obj.changeRow(-1);
                    if (success) obj.select();
                }
                else if (key == 40)
                {
                    event.returnValue = false;
                    var success = event.shiftKey ? obj.shiftRow(1) : obj.changeRow(1);
                    if (success) obj.select();
                }
            });
        };
    };
});
