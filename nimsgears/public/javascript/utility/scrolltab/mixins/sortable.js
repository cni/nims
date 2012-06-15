define([], function()
{
    return function()
    {
        // Enables sorting of table columns by text content, and can enable
        // sort on header click
        this.init_sortable = function(callback)
        {
            this.sorted_markers = [];
            this.sorted_column = 0;
            this.sorted_direction = 1;
            this.setupSortedMarkers();
            this.enableHeaderClickSorting(callback);
        };

        this.setupSortedMarkers = function()
        {
            var th_els = this._header.getElementsByTagName("th");
            var n_th_els = th_els.length;
            for (var i = 0; i < n_th_els; i++)
            {
                var text_span = document.createElement('span');
                var text_node = document.createTextNode('∧');
                text_span.className = "sorted_marker";
                text_span.style.visibility = "hidden";
                text_span.appendChild(text_node);
                text_span.style.position = 'absolute';
                th_els[i].appendChild(text_span);
                text_span.style.left = (th_els[i].offsetWidth - text_span.offsetWidth - 5) + "px";
                th_els[i].style.position = 'relative';
                this.sorted_markers.push(text_span);
            }
        };

        this.resort = function()
        {
            this.sortByColumnIndex(this.sorted_column, this.sorted_direction);
        };

        this._compare = function(a, b)
        {
            if (a < b) { return -1; }
            else if (a == b) { return 0; }
            else { return 1; }
        };

        this._sortByElement = function(th_element)
        {
            var columns = this._listToArray(this._header.getElementsByTagName('th'));
            var n_columns = columns.length;
            var column_index = columns.indexOf(th_element);
            var new_sorted_direction = (this.sorted_column == column_index) ? (-this.sorted_direction) : 1;
            this.sortByColumnIndex(column_index, new_sorted_direction);
        };

        this.sortByColumnIndex = function(column_index, direction)
        {
            var rows = this.getRows();
            var columns = this.header_elements;

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
            for (var i = 0; i < n_rows; i++)
            {
                index = sorted_rows.indexOf(sorted_rows[i]);
                inserting_node = sorted_rows[i];
                fixed_node = sorted_rows[index - 1];
                inserting_node.parentNode.insertBefore(inserting_node, fixed_node);
            }

            this.sorted_markers[this.sorted_column].style.visibility = "hidden";
            var current_marker = this.sorted_markers[column_index];
            current_marker.style.visibility = "";
            if (direction > 0)
            {
                current_marker.textContent = "∨";
            }
            else if (direction < 0)
            {
                current_marker.textContent = "∧";
            }
            this.sorted_column = column_index;
            this.sorted_direction = direction;
            this._stripe();
        };

        this.enableHeaderClickSorting = function(callback)
        {
            var ths = this._header.getElementsByTagName("th");
            var n_ths = ths.length;
            var obj = this;
            for (var i = 0; i < n_ths; i++) {
                ths[i].onclick = function () {
                    obj._sortByElement(this);
                    if (callback) callback(obj);
                }
            }
        };
    };
});
