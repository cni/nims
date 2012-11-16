define([], function()
{
    function DrilldownManager(tables, populators, auto_resize, drilldown_id)
    {
        var obj = this;
        this._tables = [];
        this._populators = [];
        tables.forEach(function(table) {
            var div = document.createElement("div");
            div.appendChild(document.createTextNode("LOADING..."));
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
        this._drilldown_id = (drilldown_id) ? drilldown_id : undefined;
        if (this._drilldown_id) { this.processHash(); }
    };

    DrilldownManager.prototype.processHash = function()
    {
        if (this._drilldown_id)
        {
            var chunks = window.location.hash.replace("#","").split(",");
            if (chunks.length && chunks[0] == this._drilldown_id)
            {
                chunks = chunks.slice(1);
                var i_chunk = 0;
                var i_table = 0;
                for (var i = 0, j = 0; i < chunks.length && j < this._tables.length; i++, j++)
                {
                    this._tables[j]._selected_rows = [{'id': chunks[i]}];
                }
            }
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
    };

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
            this.buildHash();
            table.element.focus();
        }
    };

    DrilldownManager.prototype.buildHash = function()
    {
        // Keep track of existing state in drilldown
        if (this._drilldown_id)
        {
            var drilldown_items = this._tables.slice(0, this._focus_index + 1);
            var row_ids = [];
            for (var i = 0; i < drilldown_items.length; i++)
            {
                if (drilldown_items[i]._selected_rows.length != 1) { break; }
                row_ids.push(drilldown_items[i]._selected_rows[0].id);
            }
            var items = [this._drilldown_id].concat(row_ids);
            var hash = "#" + items.join(",");
            window.location.hash = hash;
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

        // When a table (excluding the maximum index) is selected, all of its
        // nested tables should be refreshed based on the selection state
        for (var i = 0; i < this._max_index; i++)
        {
            (function()
            {
                var i_ref = i;
                obj._tables[i_ref].onSelect(function(event)
                {
                    obj.refresh(i_ref+1, event.selected_rows, event.is_instant);
                });
            })();
        }
        this._tables.forEach(function(table)
        {
            // Clicking on a table should trigger a selection
            table.element.addEventListener("click", function(event)
            {
                obj.selectTable(table);
            });
            // Keydown left or right triggers moving to previous or next
            // selected table, respectively
            table.element.addEventListener("keydown", function(event)
            {
                var key = event.keyCode;
                if (key == 37) // left arrow
                {
                    obj.focusPrev();
                }
                else if (key == 39) // right arrow
                {
                    obj.focusNext();
                }
            });
            // When a table is selected, the link hash should be rebuilt
            table.onSelect(function(event) {
                obj.buildHash();
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
