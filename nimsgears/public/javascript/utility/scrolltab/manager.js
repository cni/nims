define([], function()
{
    function ScrolltableDrilldown(tables, populators)
    {
        var obj = this;
        this._tables = [];
        this._populators = [];
        tables.forEach(function(table) { obj._tables.push(table); });
        populators.forEach(function(populator) { obj._populators.push(populator); });
        this._unlocked = true;
        this._focus_index = 0;
        this._max_index = this._tables.length - 1;
    };

    ScrolltableDrilldown.prototype.enableKeyboardNavigation = function()
    {
        var obj = this;
        var n_tables = this._tables.length;
        for (var i = 0; i < this._max_index; i++)
        {
            (function()
            {
                var next_table = obj._tables[i+1];
                obj._tables[i].onSelect(function(event)
                {
                    var table_data = obj._populators[i](event);
                    next_table.populateTable(table_data);
                    next_table.enableMouseSelection();
                });
            })();
        }
        this._tables.forEach(function(table)
        {
            table.element.addEventListener("focus", function(event)
            {
                if (table.getRows().length == 0)
                {
                    table.element.blur();
                }
                else
                {
                    obj._focus_index = obj._tables.indexOf(table);
                    for (var i = obj._max_index; i > obj._focus_index; i--)
                    {
                        obj._tables[i].cleanUp();
                    }
                    table.select();
                }
            });
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
    };

    ScrolltableDrilldown.prototype.tableInFocus = function()
    {
        return this._tables[this._focus_index];
    };

    ScrolltableDrilldown.prototype.focusNext = function()
    {
        if (this._unlocked &&
            this.tableInFocus().onlyOneSelected() &&
            (this._focus_index != this._max_index))
        {
            this._focus_index++;
            this._tables[this._focus_index].element.focus();
            this._tables[this._focus_index].changeRow(1);
        }
    };

    ScrolltableDrilldown.prototype.focusPrev = function()
    {
        if (this._unlocked && (this._focus_index > 0))
        {
            this._tables[this._focus_index].cleanUp();
            this._focus_index--;
            this._tables[this._focus_index].element.focus();
        }
    };

    return ScrolltableDrilldown;
});


