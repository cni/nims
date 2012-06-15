define([], function()
{
    function DrilldownManager(tables, populators, auto_resize)
    {
        var obj = this;
        this._tables = [];
        this._populators = [];
        tables.forEach(function(table) {
            var div = document.createElement("div");
            div.appendChild(document.createTextNode("LOADING"));
            obj._tables.push(table);
            table.setLoadingDiv(div);
            });
        populators.forEach(function(populator) { obj._populators.push(populator); });
        this._unlocked = true;
        this._focus_index = 0;
        this._max_index = this._tables.length - 1;
        this.nav_timeout = null;
        this.enableKeyboardNavigation();
        if (auto_resize)
        {
            var resize = this.getResize(125);
            window.addEventListener('resize', resize);
            resize();
        }
    };

    DrilldownManager.prototype.getResize = function(space_from_bottom)
    {
        var obj = this;
        return function(event) {
            var window_height = window.innerHeight;
            var distance_to_top = 0;
            for (var el = obj._tables[0].element; el != null; el = el.offsetParent)
            {
                distance_to_top += el.offsetTop;
            }

            var computed_height = window_height - distance_to_top - space_from_bottom;
            computed_height = (computed_height < 200) ? 200 : computed_height;
            for (var i = 0; i < obj._tables.length; i++)
            {
                obj._tables[i]._body.style.height = computed_height + "px";
            }
        }
    }

    DrilldownManager.prototype.getPopulateNextTable = function()
    {
        var obj = this;
        return function(next_table, table_data)
        {
            next_table.stopLoading();
            next_table.populateTable(table_data);
            next_table.resort();
            next_table.enableMouseSelection();
            obj._unlocked = true;
        };
    };

    DrilldownManager.prototype.refresh = function(index, selected_rows, is_instant)
    {
        var obj = this;
        var table = this._tables[index];
        var populator = this._populators[index];
        table.emptyTable();
        this._unlocked = false;
        if (is_instant === undefined) is_instant = false;
        if (is_instant)
        {
            clearTimeout(this.nav_timeout);
            table.startLoading();
            populator(table, selected_rows, is_instant, this.getPopulateNextTable());
            this.nav_timeout = null;
        }
        else
        {
            if (this.nav_timeout)
            {
                clearTimeout(this.nav_timeout);
            }
            this.nav_timeout = setTimeout(function()
            {
                table.startLoading();
                populator(table, selected_rows, is_instant, obj.getPopulateNextTable());
                obj.nav_timeout = null;
            }, 250);
        }
    }

    DrilldownManager.prototype.selectTable = function(table)
    {
        // The table is empty, remove focus from it immediately
        if (table.getRows().length == 0)
        {
            table.element.blur();
            this.tableInFocus().element.focus();
        }
        else
        {
            // Table has data, so clean up nested tables and repopulate
            // the nested with a select call
            this._focus_index = this._tables.indexOf(table);
            for (var i = this._max_index; i > (this._focus_index + 1); i--)
            {
                this._tables[i].cleanUp();
            }
            if (table._selected_rows.length == 0) { table.changeRow(1); table.select(); }
            table.element.focus();
        }
    };

    DrilldownManager.prototype.nextTable = function()
    {
        var index = this._focus_index + 1;
        return (index > this._max_index) ? false : this._tables[index];
    };

    DrilldownManager.prototype.enableKeyboardNavigation = function()
    {
        var obj = this;
        for (var i = 0; i < this._max_index; i++)
        {
            (function()
            {
                var next_table = obj._tables[i+1];
                var populator = obj._populators[i];
                var i_ref = i;
                obj._tables[i_ref].onSelect(function(event)
                {
                    obj.refresh(i_ref+1, event.selected_rows, event.is_instant);
                });
            })();
        }
        this._tables.forEach(function(table)
        {
            table.element.addEventListener("click", function(event)
            {
                obj.selectTable(table);
                if (obj.nextTable())
                {
                    obj.nextTable().deselectAll();
                }
            });
            table.element.addEventListener("keydown", function(event)
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

    DrilldownManager.prototype.tableInFocus = function()
    {
        return this._tables[this._focus_index];
    };

    DrilldownManager.prototype.focusNext = function()
    {
        if (this._unlocked &&
            this.tableInFocus().onlyOneSelected() &&
            (this._focus_index != this._max_index))
        {
            this._focus_index++;
            this._tables[this._focus_index].changeRow(1);
            this._tables[this._focus_index].element.focus();
            this._tables[this._focus_index].select();
        }
    };

    DrilldownManager.prototype.focusPrev = function()
    {
        if (this._unlocked && (this._focus_index > 0))
        {
            this.tableInFocus().deselectAll();
            this._focus_index--;
            this.selectTable(this.tableInFocus());
        }
    };

    return DrilldownManager;
});


