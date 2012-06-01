define([], function()
{
    function ScrolltableDrilldown(table_array)
    {
        var obj = this;
        this._tables = [];
        table_array.forEach(function(table) { obj._tables.push(table); });
        this._unlocked = true;
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
                if (key == 37)
                {
                    obj.focusPrev();
                }
                else if (key == 39)
                {
                    obj.focusNext();
                }
            });
        });

    }

    ScrolltableDrilldown.prototype.focusNext = function()
    {
        if (this._unlocked && (this._focus_index != this._max_index))
        {
            this._focus_index++;
            this._tables[this._focus_index].element.focus();
        }
    };

    ScrolltableDrilldown.prototype.focusPrev = function()
    {
        if (this._unlocked && (this._focus_index != 0))
        {
            this._focus_index--;
            this._tables[this._focus_index].element.focus();
        }
    };

    return ScrolltableDrilldown;
});


