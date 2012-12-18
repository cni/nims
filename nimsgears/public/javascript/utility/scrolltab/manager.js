define([], function()
{
    /* DrilldownManager Constructor
     *
     * tables - list of drilldown tables in the order they'll be drilled down
     * populators - list of callbacks to populate each of the respective
     *      drilldown tables
     * auto_resize - bool for whether table should resize to fit browser window
     * drilldown_id - id/name to be used in URL for linking back to table
     *      state. if left undefined, no url is built up
     */
    function DrilldownManager(tables, populators, auto_resize, drilldown_id)
    {
        var obj = this;
        this._tables = [];
        this._populators = [];

        // Configure loadable mixin and populate table listing
        tables.forEach(function(table) {
            obj._tables.push(table);

            // Create/set loading div
            var div = document.createElement("div");
            div.appendChild(document.createTextNode("LOADING..."));
            table.setLoadingDiv(div);
            });
        populators.forEach(function(populator) { obj._populators.push(populator); });

        // Lock to prevent rapid scrolling between tables which are not loaded yet
        this._unlocked = true;

        // Track table in focus
        this._focus_index = 0;
        this._max_index = this._tables.length - 1;

        // Nav timeout used to limit number of server requests issued - when a
        // response is desired 250 ms must pass without another request before
        // it will ship it out
        this.nav_timeout = null;
        this.nav_timeout_ms = 250;
        this.enableKeyboardNavigation();
        if (auto_resize)
        {
            var resize = this.getResize(125);
            window.addEventListener('resize', resize);
            resize();
        }

        // If they specified a drilldown id/name, start off the table load with
        // a processing of the hash to return to the desired state
        this._drilldown_id = (drilldown_id) ? drilldown_id : undefined;
        if (this._drilldown_id) { this.processHash(); }
    };

    /*
     * processHash
     * If a drilldown_id was specified, processes URL hash to return page to a
     * given state.
     */
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

    /*
     * getResize
     * Returns resize function to be used with window resize events.
     *
     * space_from_bottom - number of pixels you'd like to leave as a buffer
     *      from bottom of the page
     */
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

    /*
     * getPopulateNextTable
     * Returns function that, when passed the next table and the relevant data,
     * handles populating the table in a manner consistent with the drilldown
     * (unlocks when complete, resorts entries, deals with loading div.
     */
    DrilldownManager.prototype.getPopulateNextTable = function()
    {
        var obj = this;
        /*
         * next_table - next drilldown object in sequence
         * table_data - data to populate next table with (see populateTable in
         *      scrolltable docs)
         */
        return function(next_table, table_data)
        {
            next_table.stopLoading();
            next_table.populateTable(table_data);
            next_table.resort();
            next_table.enableMouseSelection();
            obj._unlocked = true;
        };
    };

    /*
     * refresh
     * Reload the drilldown from a given index with a given context
     * (selected_rows). Whether or nor the load happens immediately or after
     * waiting for the nav_timeout is specified by is_instant.
     *
     * index - index of the table to be refreshed from
     * selected_rows - list of rows that were clicked in the previous (in
     *      drilldown order) table for clarity regarding what to populate the
     *      next table with
     * is_instant - bool to express whether load should happen immediately or
     *      after nav_timeout (default: false)
     */
    DrilldownManager.prototype.refresh = function(index, selected_rows, is_instant)
    {
        var obj = this;
        var table = this._tables[index];
        var populator = this._populators[index];
        table.emptyTable();

        // Lock table to ensure further loads/drilldowns do not occur
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
            }, this.nav_timeout_ms);
        }
    };

    /*
     * selectTable
     * Handles selecting specified drilldown scrolltable in a manner consistent
     * with drilldowns. Specifically, clears out nested tables and handles
     * focus (or in the case of an empty table, nothing). Hash is built up if
     * table is selected and URL hashing is enabled.
     *
     * table - drilldown scrolltable object to be selected
     */
    DrilldownManager.prototype.selectTable = function(table)
    {
        // The table is empty, remove focus from it immediately
        if (table.getRows().length == 0)
        {
            table.element.blur();
            // currently points to last table in focus prior to this call
            this.tableInFocus().element.focus();
        }
        else
        {
            // Table has data, so clean up nested tables and activate a focus
            // on the table
            this._focus_index = this._tables.indexOf(table);
            for (var i = this._max_index; i > (this._focus_index + 1); i--)
            {
                this._tables[i].cleanUp();
            }
            this.buildHash();
            table.element.focus();
        }
    };

    /*
     * buildHash
     * Given current table state, set URL to contain hash to current table
     * state.
     */
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

    /*
     * nextTable
     * Return next table (beyond table focus). If at max, returns false.
     */
    DrilldownManager.prototype.nextTable = function()
    {
        var index = this._focus_index + 1;
        return (index > this._max_index) ? false : this._tables[index];
    };

    /*
     * enableKeyboardNavigation
     * Sets up keyboard events to allow navigation about the table, as well as
     * events to handle populating relevant data based on said navigation.
     */
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

    /*
     * tableInFocus
     */
    DrilldownManager.prototype.tableInFocus = function()
    {
        return this._tables[this._focus_index];
    };

    /*
     * focusNext
     * Shift focus to next table. Used in keyboard navigation for drilling
     * down. Respects table locking to prevent several from being fired before
     * they've finished.
     */
    DrilldownManager.prototype.focusNext = function()
    {
        // Checks that table is unlocked, only one row is selected (allowing
        // for drilldown to make sense), and that we're not on the maximum
        // index
        if (this._unlocked &&
            this.tableInFocus().onlyOneSelected() &&
            (this._focus_index != this._max_index))
        {
            // Supposing conditions pass, we select the first row (default row
            // in a fresh table load is -1, so we select the first row, focus
            // on the table, and call select to fire any relevant events
            this._focus_index++;
            this._tables[this._focus_index].changeRow(1);
            this._tables[this._focus_index].element.focus();
            this._tables[this._focus_index].select();
        }
    };

    /*
     * focusPrev
     * Shift focus to previous table. Used in keyboard navigation for
     * navigating out. Respects table locking to prevent several from being
     * fired before they've finished.
     */
    DrilldownManager.prototype.focusPrev = function()
    {
        // Checks that table is unlocked, and we're not on the first drilldown.
        if (this._unlocked && (this._focus_index > 0))
        {
            // Supposing conditions pass, we deselect all rows in the current
            // table and zoom out on drill down level. We then select this new
            // table (without reloading its content).
            this.tableInFocus().deselectAll();
            this._focus_index--;
            this.selectTable(this.tableInFocus());
        }
    };

    return DrilldownManager;
});
