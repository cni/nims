define(['./selectable'], function(asSelectable)
{
    return function()
    {
        asSelectable.call(this);

        this.init_kbsupport = function()
        {
            this.init_selectable();
            this.enableKeyboardSelection();
        };

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
                rows[change_to_index].scrollIntoViewIfNeeded(direction <= 0);
                success = true;
            }
            return success;
        };

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
                rows[change_to_index].scrollIntoViewIfNeeded(direction <= 0);
                success = true;
            }
            return success;
        };

        this.enableKeyboardSelection = function()
        {
            var obj = this;
            this.element.setAttribute("tabindex", 0);
            this.element.addEventListener("keydown", function(event)
            {
                var key = event.keyCode;
                if (key == 38)
                {
                    var success = event.shiftKey ? obj.shiftRow(-1) : obj.changeRow(-1);
                    if (success) obj.select();
                }
                else if (key == 40)
                {
                    var success = event.shiftKey ? obj.shiftRow(1) : obj.changeRow(1);
                    if (success) obj.select();
                }
            });
        };
    };
});
