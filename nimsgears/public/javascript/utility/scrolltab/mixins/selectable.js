define([], function()
{
    return function()
    {
        /*
         * Provides all necessary functionality to have single and batch
         * selectable/deselectable rows. Also contains function to enable mouse
         * functionality to this end.
         */
        this.init_selectable = function() {
            this._onSelect = [];
            this._selected_rows = [];
            this.last_clicked_index = -1;
            this.shift_clicked_index = -1;
            this.enableMouseSelection();
        };

        /*
         * select
         * Hands off the currently selected rows in the table to all functions
         * that have been specified with onSelect. They are given a structure
         * with three entries: .selected_rows, .table (a pointer to the table
         * we're within), and .is_instant.
         *
         * is_instant - whether or not the selection should respond immediately
         *      or wait for some configured delay (delay has to be handled by
         *      the onSelect functions - you could certainly ignore this
         *      functionality if you so choose)
         */
        this.select = function(is_instant)
        {
            if (is_instant === undefined) is_instant = false;
            var obj = this;
            this._updateSelectedRows();
            this._onSelect.forEach(function(fn)
            {
                fn(
                {
                    selected_rows: obj._selected_rows,
                    table: obj,
                    is_instant: is_instant,
                });
            });
        };

        /*
         * onSelect
         * Adds function to list of callbacks to occur when a select is issued
         * on the table.
         *
         * fn - function that accepts a dictionary as an argument (see select
         * for explanation of contents)
         */
        this.onSelect = function(fn)
        {
            this._onSelect.push(fn);
        };

        /*
         * deselectAll
         * Deselects all rows in the table (removes from data structures
         * tracking selections as well as removes the ui-selected class from
         * them).
         */
        this.deselectAll = function()
        {
            this.last_clicked_index = this.shift_clicked_index = -1;
            this._selected_rows = [];
            this.getRows().forEach(function(row)
            {
                row.classList.remove("ui-selected");
            });
        };

        /*
         * cleanUp
         * Resets table state back to original state (no contents, no selected
         * rows, all data structures tracking info on table reset).
         */
        this.cleanUp = function()
        {
            this.emptyTable();
            this.last_clicked_index = this.shift_clicked_index = -1;
            this._selected_rows = [];
        };

        /*
         * onlyOneSelected
         * Convenience function to return whether or not only one row is
         * selected in the table.
         */
        this.onlyOneSelected = function()
        {
            return (this._selected_rows.length == 1);
        }

        /*
         * _batchSelect
         * Used internally to handle batch selection. Can specify whether you'd
         * like to deselect or select everything within set of specified rows
         * between the given indices.
         *
         * rows - rows selection is being performed on
         * a - one boundary index of the selection (can be high or low)
         * b - other boundary index of the selection
         * with_value - false or true based on whether you're deselecting or
         *      selecting rows, respectively
         */
        this._batchSelect = function(rows, a, b, with_value)
        {
            var subset;
            if (a == b) {
                subset = [rows[a]];
            } else if (a < b) {
                subset = rows.slice(a, b + 1);
            } else if (a > b) {
                subset = rows.slice(b, a + 1);
            }

            var n_subset = subset.length;
            if (with_value)
            {
                for (var i = 0; i < n_subset; i++)
                {
                    subset[i].classList.add("ui-selected");
                }
            }
            else
            {
                for (var i = 0; i < n_subset; i++)
                {
                    subset[i].classList.remove("ui-selected");
                }
            }
        };

        /*
         * toggleSelect
         * Switch the selection state of a row to selected or unselected based
         * on to_value.
         *
         * to_value - whether you'd like the row selected (true) or deselected
         *      (false)
         */
        this._toggleSelect = function(row, to_value)
        {
            if (row.classList.contains("ui-selected") || ((to_value !== undefined) && to_value == false))
            {
                row.classList.remove("ui-selected");
            }
            else
            {
                row.classList.add("ui-selected");
            }
        };

        /*
         * getSingleSelectCallback
         * Returns function to be called when a single row is clicked on.
         */
        this._getSingleSelectCallback = function()
        {
            var obj = this;
            return function(event)
            {
                if (!(event.shiftKey || event.metaKey || event.ctrlKey))
                {
                    var row_list = obj.getRows();
                    var index_clicked = row_list.indexOf(this);

                    obj.last_clicked_index = index_clicked;
                    obj.shift_clicked_index = index_clicked;

                    row_list.map(function(row)
                    {
                        row.classList.remove("ui-selected");
                    });
                    this.classList.add("ui-selected");

                    obj.select();
                }
            }
        };

        /*
         * getMultiSelectCallback
         * Returns function to be called when multiple rows are selected (such
         * as with a batch select key). Differentiates between shift and ctrl -
         * similar to Apple's Finder.
         */
        this._getMultiSelectCallback = function()
        {
            var obj = this;
            return function(event)
            {
                var row_list = obj.getRows();
                var index_clicked = row_list.indexOf(this);
                if (event.shiftKey)
                {
                    var last = obj.last_clicked_index;
                    var shift = obj.shift_clicked_index;
                    if (last != index_clicked)
                    {
                        obj._batchSelect(row_list, last, shift, false);
                        obj._batchSelect(row_list, last, index_clicked, true);
                        obj.shift_clicked_index = index_clicked;
                    }

                    obj.select();
                }
                else if (event.metaKey || event.ctrlKey)
                {
                    obj._toggleSelect(this);
                    if (this.classList.contains("ui-selected"))
                    {
                        obj.last_clicked_index = index_clicked;
                        obj.shift_clicked_index = index_clicked;
                    } else {
                        obj.last_clicked_index = obj.shift_clicked_index = -1;
                    }

                    obj.select();
                }
            };
        };

        /*
         * _updateSelectedRows
         * Internal function to update state of _selected_rows field based on
         * table state.
         */
        this._updateSelectedRows = function()
        {
            this._selected_rows = this._listToArray(this._body.getElementsByClassName("ui-selected"));
        };

        /*
         * synchronizeSelections
         * After you repopulate the table, synchronizeSelections can be called
         * to reselect entries that were previously selected in the table.
         * Basically takes advantage of momentary lapse in synchrony between
         * recorded table state and _selected_rows from the selectable mixin
         * when a table is repopulated. Requires that the rows have unique ids
         * set - otherwise there's no reliable way to match selections.
         */
        this.synchronizeSelections = function()
        {
            // XXX This function requires rows have ids set. XXX
            // Takes old selected rows and checks against rows that are
            // currently in the table - overlapping rows are selected to ensure
            // if you repopulate the table you don't lose that information.
            var obj = this;
            // Add the old selected rows to a dictionary by id
            var id_to_row_dict = [];
            this._selected_rows.map(function(row)
            {
                id_to_row_dict[row.id] = row;
            });

            // Iterate through current rows, checking against the old selected
            // rows and re-selecting where relevant
            var rows = this.getRows();
            var n_rows = rows.length;
            for (var i = 0; i < n_rows; i++)
            {
                if (rows[i].id != "" && id_to_row_dict.hasOwnProperty(rows[i].id))
                {
                    rows[i].classList.add("ui-selected");
                    obj.last_clicked_index = obj.shift_clicked_index = i;
                }
            }
            this._updateSelectedRows();
        };

        /*
         * enableMouseSelection
         * Enables single and multi select (ctrl and shift key) on table.
         */
        this.enableMouseSelection = function()
        {
            var rows = this.getRows();
            var obj = this;
            rows.map(function(row) {
                row.addEventListener("mouseup", obj._getSingleSelectCallback());
                row.addEventListener("mousedown", obj._getMultiSelectCallback());
            });
        };
    };
});
