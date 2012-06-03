define([], function()
{
    return function()
    {
        // we do this so we don't wind up sharing variables across instances...
        // this refers to the prototype so if you set crap on it you will find
        // yourself very unhappy
        this.init_selectable = function() {
            this._onSelect = [];
            this._selected_rows = [];
            this.last_clicked_index = -1;
            this.shift_clicked_index = -1;
            this.enableMouseSelection();
        };

        this.select = function()
        {
            var obj = this;
            this._updateSelectedRows();
            this._onSelect.forEach(function(fn)
            {
                fn(
                {
                    selected_rows: obj._selected_rows,
                    table: obj
                });
            });
        };

        this.onSelect = function(fn)
        {
            this._onSelect.push(fn);
        };

        this.deselectAll = function()
        {
            this.last_clicked_index = this.shift_clicked_index = -1;
            this._selected_rows = [];
            this.getRows().forEach(function(row)
            {
                row.classList.remove("ui-selected");
            });
        };

        this.cleanUp = function()
        {
            this.emptyTable();
            this.last_clicked_index = this.shift_clicked_index = -1;
            this._selected_rows = [];
        };

        this.onlyOneSelected = function()
        {
            return (this._selected_rows.length == 1);
        }

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
                    }

                    obj.select();
                }
            };
        };

        this._updateSelectedRows = function()
        {
            this._selected_rows = this._listToArray(this._body.getElementsByClassName("ui-selected"));
        };

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
                if (id_to_row_dict.hasOwnProperty(rows[i].id))
                {
                    rows[i].classList.add("ui-selected");
                    obj.last_clicked_index = obj.shift_clicked_index = i;
                }
            }
            this._updateSelectedRows();
        };

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
