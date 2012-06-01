define([], function()
{
    function ScrolltableDrilldown(table_array)
    {
        this._tables = [];
        table_array.forEach(function(table) { this._tables.push(table); });
        this._focus_index = 0;
        this._max_index = this._tables.length - 1;
    };

    ScrolltableDrilldown.prototype.enableKeyboardNavigation = function()
    {
        var obj = this;
        this._tables.forEach(function(table)
        {
            table.element.addEventListener("keyup", function(event)
            {
                var key = event.keyCode;
                if (key

            });
        });

    }

    ScrolltableDrilldown.prototype.focusNext = function()
    {
        if (this._unlocked && (this._focus_index != this._max_index))
        {
            this._focus_index++;
        }
    };

    ScrolltableDrilldown.prototype.focusPrev = function()
    {
        if (this._unlocked && (this._focus_index != 0))
        {
            this._focus_index--;
        }
    };

    return ScrolltableDrilldown;
};


