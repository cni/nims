define([], function() {
    var asSortable = function() {
        // Enables sorting of table columns by text content, and can enable
        // sort on header click
        this.sorted_column = 0;
        this.sorted_direction = 1;

        this.resort = function() {
            this.sortByColumnIndex(this.sorted_column, this.sorted_direction);
        };

        this._compare = function(a, b) {
            if (a < b) { return -1; }
            else if (a == b) { return 0; }
            else { return 1; }
        };

        this._indexOf = function(element, in_array) {
            var n_elements = in_array.length;
            var index = -1;
            for (var i = 0; i < n_elements; i++) {
                if (in_array[i] === element) {
                    index = i;
                    break;
                }
            }
            return index;
        }

        this._sortByElement = function(th_element) {
            var columns = this._listToArray(this._header.getElementsByTagName("th"));
            var n_columns = columns.length;
            var column_index = columns.indexOf(th_element);
            var new_sorted_direction = (this.sorted_column == column_index) ? (-this.sorted_direction) : 1;
            this.sortByColumnIndex(column_index, new_sorted_direction);
        };

        this.sortByColumnIndex = function(column_index, direction) {
            var rows = this.getRows();

            // First operation determines order rows go in:
            // We actually do this in reverse of desired order and then put them
            // all in place backwards
            var cell_text_a;
            var cell_text_b;
            var obj = this;
            var sorted_rows = rows.sort(function(a, b)
            {
                cell_text_a = a.children[column_index].textContent;
                cell_text_b = b.children[column_index].textContent;
                return -direction * obj._compare(cell_text_a, cell_text_b);
            });

            // Second puts them in the proper order:
            // With them all sorted 'backwards', we go through all the items besides
            // the first, and stick them in front of each other.  By the end, we have
            // our list sorted.
            var index;
            var inserting_node;
            var fixed_node;
            var n_rows = sorted_rows.length;
            for (var i = 0; i < n_rows; i++) {
                index = sorted_rows.indexOf(sorted_rows[i]);
                inserting_node = sorted_rows[i];
                fixed_node = sorted_rows[index - 1];
                inserting_node.parentNode.insertBefore(inserting_node, fixed_node);
            }

            this.sorted_column = column_index;
            this.sorted_direction = direction;
            this._stripe();
        };

        this.enableHeaderClickSorting = function()
        {
            var ths = this._header.getElementsByTagName("th");
            var n_ths = ths.length;
            var obj = this;
            for (var i = 0; i < n_ths; i++) {
                ths[i].onclick = function () {
                    obj._sortByElement(this);
                }
            }
        };
    };

    var asLoadable = function() {
        // Allows insertion of a loader div to be displayed when table is in
        // process of loading. Hides table content and shows loader div, then
        // redisplays table when stopLoading called.
        this.timeout = 250; // ms
        this._loading_timeout;
        this._loading_div;

        this._getBodyTable = function() {
            return this._body.getElementsByTagName("table")[0];
        };

        this.setLoadingDiv = function(loading_div) {
            loading_div.hidden = true;
            var body_table = this._getBodyTable();
            this._body.insertBefore(loading_div, body_table);
            this._loading_div = loading_div;
        };

        this.startLoading = function() {
            if (this._loading_timeout) {
                clearTimeout(this._loading_timeout);
                this._loading_timeout = null;
            }
            var obj = this;
            this._loading_timeout = setTimeout(function() {
                var body_table = obj._getBodyTable();
                body_table.hidden = true;
                obj._loading_div.hidden = false;
            }, this.timeout);
        };

        this.stopLoading = function()
        {
            clearTimeout(this._loading_timeout);
            this._getBodyTable().hidden = false;
            this._loading_div.hidden = true;
        };
    };

    var asSelectable = function() {
        this.last_clicked_index = 0;
        this.shift_clicked_index = 0;

        this._batchSelect = function(rows, a, b, with_value) {
            var subset;
            if (a == b) {
                subset = [rows[a]];
            } else if (a < b) {
                subset = rows.slice(a, b + 1);
            } else if (a > b) {
                subset = rows.slice(b, a + 1);
            }

            if (with_value) {
                var n_subset = subset.length;
                for (var i = 0; i < n_subset; i++) {
                    if (!subset[i].classList.contains("ui-selected")) {
                        subset[i].classList.add("ui-selected");
                    }
                }
            } else {
                for (var i = 0; i < n_subset; i++) {
                    subset[i].classList.remove("ui-selected");
                }
            }
        }

        this._getSingleSelectCallback = function() {
            var obj = this;
            return function(event) {
                if (!(event.shiftKey || event.metaKey || event.ctrlKey)) {
                    var row_list = obj.getRows();
                    var index_clicked = row_list.indexOf(this);

                    obj.last_clicked_index = index_clicked;
                    obj.shift_clicked_index = index_clicked;

                    row_list.map(function(row) {
                        row.classList.remove("ui-selected");
                    });
                    this.classList.add("ui-selected");

                    //select();
                }
            }
        }

        this._toggleSelect = function(row) {
            if (row.classList.contains("ui-selected")) {
                row.classList.remove("ui-selected");
            } else {
                row.classList.add("ui-selected");
            }
        };

        this._getMultiSelectCallback = function() {
            var obj = this;
            return function(event) {
                var row_list = obj.getRows();
                var index_clicked = row_list.indexOf(this);
                if (event.shiftKey) {
                    var last = obj.last_clicked_index;
                    var shift = obj.shift_clicked_index;
                    if (last != index_clicked) {
                        obj._batchSelect(row_list, last, shift, false);
                        obj._batchSelect(row_list, last, index_clicked, true);
                        obj.shift_clicked_index = index_clicked;
                    }

                    //select();
                }
                else if (event.metaKey || event.ctrlKey)
                {
                    obj._toggleSelect(this);
                    if (this.classList.contains("ui-selected"))
                    {
                        obj.last_clicked_index = index_clicked;
                        obj.shift_clicked_index = index_clicked;
                    }

                    //select();
                }
            };
        };

        this.enableClickSelection = function() {
            var rows = this.getRows();
            var obj = this;
            rows.map(function(row) {
                row.addEventListener("mouseup", obj._getSingleSelectCallback());
                row.addEventListener("mousedown", obj._getMultiSelectCallback());
            });
        }
    };

    return {
        asSortable: asSortable,
        asLoadable: asLoadable,
        asSelectable: asSelectable,
    };
});
