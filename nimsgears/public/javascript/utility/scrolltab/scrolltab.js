define([], function()
{
    /*
     * Scrolltable Constructor
     *
     * table_id - id of table to convert to a scrolltable
     * title - title you'd like displayed over the scrolltable
     */
    function Scrolltable(table_id, title) {
        this.element;
        this._header;
        this._body;
        this._title;
        if (table_id !== undefined)
        {
            this._original = document.getElementById(table_id);
            this._original.hidden = true;
            this.title = (title !== undefined) ? document.createTextNode(title) : undefined;
            this.render();
        }
    }

    /*
     * flattenElement
     * Used to remove all height from an element. Used to take advantage of the
     * width constraining properties of an element without leaving it
     * displayed. Primary use case is for flattening the header of a table
     * while still allowing properties on its header elements to constrain
     * properties of the body.
     *
     * el - element to flatten
     */
    Scrolltable.prototype._flattenElement = function(el) {
        var children = el.childNodes;
        var n_children = children.length;
        for (var i = 0; i < n_children; i++) {
            this._flattenElement(children[i]);
        }
        var el_style = el.style;
        if (el_style) {
            el_style.marginTop = 0 + "px";
            el_style.marginBottom = 0 + "px";
            el_style.paddingTop = 0 + "px";
            el_style.paddingBottom = 0 + "px";
            el_style.height = 0 + "px";
            el_style.lineHeight = 0 + "px";
            el_style.overflow = "hidden";
        }
    }

    /*
     * _stripe
     * Applies stripe class to every other row in table.
     */
    Scrolltable.prototype._stripe = function() {
        var rows = this.getRows();
        n_rows = rows.length;
        for (var i = 0; i < n_rows; i++) {
            rows[i].classList.remove("stripe");
            if (i % 2 == 0) {
                rows[i].classList.add("stripe");
            }
        }
    }

    /*
     * _listToArray
     * Used to convert standard js lists into Arrays to receive the additional
     * functionality. getElementsByTagName returns elements as a list, so we
     * call this on the return value to get the extra functionality we'd like.
     *
     * list - javascript list to be return as proper Array
     */
    Scrolltable.prototype._listToArray = function(list)
    {
        var arr = new Array();
        var n_els = list.length
        for (var i = 0; i < n_els; i++) {
           arr.push(list[i]);
        }
        return arr;
    }


    /*
     * getRows
     * Return Array of all rows in table.
     */
    Scrolltable.prototype.getRows = function() {
        var rows = this._body.getElementsByTagName("tbody")[0].getElementsByTagName("tr");
        return this._listToArray(rows);
    }

    /*
     * render
     * Performs the actual in-place swap of the old table with the new.
     */
    Scrolltable.prototype.render = function() {
        /*
        We render 2 (optionally 3) divs above each other. (Title), header, body.

        The original table is cloned twice, once for the header, once for the body.

        In the header, we remove the tbody element. In the body, we flatten the
        thead element.

        The thead is not outright removed because it can be used to maintain
        identical TD widths in the body div. Set a style for the thead, and it will
        hold across divs to create the appearance of a vanilla table - just with
        the option of making a scrolltable body.
        */
        this.element = document.createElement('div');
        this.element.className = "scrolltable_wrapper"
        this.element.id = this._original.id;

        if (this.title !== undefined) {
            this._title = document.createElement('div');
            this._title.classList.add("scrolltable_title");
            this._title.appendChild(this.title);
            this.element.appendChild(this._title);
        }

        this.element.appendChild(this.createSpacer());

        this._header = document.createElement('div');
        this._header.className = "scrolltable_header";
        this.element.appendChild(this._header);

        this.element.appendChild(this.createSpacer());

        this._body = document.createElement('div');
        this._body.className = "scrolltable_body";
        this.element.appendChild(this._body);

        this.element.appendChild(this.createSpacer());

        var table = this._original.cloneNode(true);
        table.setAttribute("cellpadding",0);
        table.setAttribute("cellspacing",0);
        table.hidden = false;
        table.id = null;
        table.className = "scrolltable";

        // Header body removal
        var table_bodyless = table.cloneNode(true);
        this._header.appendChild(table_bodyless);
        table_bodyless.removeChild(table_bodyless.getElementsByTagName("tbody")[0]);

        // Body header flattening
        var table_headerless = table.cloneNode(true);
        this._body.appendChild(table_headerless);
        var thead = table_headerless.getElementsByTagName("thead")[0];
        this._flattenElement(thead);

        // We need to replace the element now so we can compute offsetHeight - this
        // allows us to yank up the body using a negative margin. This is because
        // despite flattening the header, it has SOME height (you can get rid of
        // this with display:block, but then the formatting on the TH no longer
        // holds).
        this._original.parentNode.replaceChild(this.element, this._original);
        var thead_height = thead.offsetHeight;
        this._header.style.marginBottom = -thead_height + "px";
        this._stripe();
        table_bodyless.style.visibility = "";
        table_headerless.style.visibility = "";
    }

    /*
     * createSpacer
     * Creates and returns a spacer element that forces elements to line up
     * properly within the parent div.
     */
    Scrolltable.prototype.createSpacer = function()
    {
        var spacer = document.createElement("div");
        spacer.style.clear = "both";
        return spacer;
    }

    /*
     * createTableRowFromTuple
     * Creates a table row from a list of strings, with each string getting its
     * own cell.
     *
     * text_tuple - list of strings to be converted into a table row
     */
    Scrolltable.prototype.createTableRowFromTuple = function(text_tuple)
    {
        var td;
        var tr = document.createElement('tr');
        var n_elements = text_tuple.length;
        for (var i = 0; i < n_elements; i++)
        {
            td = document.createElement('td');
            td.textContent = text_tuple[i];
            tr.appendChild(td);
        }
        return tr;
    };

    /*
     * emptyTable
     * Remove all rows from table - emptying it out.
     */
    Scrolltable.prototype.emptyTable = function()
    {
        var rows = this.getRows();
        var n_rows = rows.length;
        var tbody = this._body.getElementsByTagName("tbody")[0];
        for (var i = 0; i < n_rows; i++)
        {
            tbody.removeChild(rows[i]);
        }
    }

    /*
     * populateTable
     * Populate table with rows (as well as the relevant attributes) based on
     * table_dict.
     *
     * table_dict - relevant data (in the form of a dictionary containing
     *      'data', with nested keys 'data' (list of tuples for data in each
     *      row - see createTableRowFromTuple) and 'attrs' (dictionary of
     *      attributes to be applied to each row, e.g. {'class': 'important',
     *      'id': 'exp_33'})
     */
    Scrolltable.prototype.populateTable = function(table_dict)
    {
        this.emptyTable();
        if (table_dict['data'])
        {
            var row;
            var tbody = this._body.getElementsByTagName("tbody")[0];
            var n_elements = table_dict['data'].length;
            for (var i = 0; i < n_elements; i++)
            {
                row = this.createTableRowFromTuple(table_dict['data'][i]);
                if (table_dict.hasOwnProperty('attrs'))
                {
                    for (var attr in table_dict['attrs'][i]) {
                        if (table_dict['attrs'][i].hasOwnProperty(attr)) {
                            row.setAttribute(attr, table_dict['attrs'][i][attr]);
                        }
                    }
                }
                tbody.appendChild(row);
            }
            this._stripe();
        }
    };

    /*
     * onDoubleClick
     * Set callback to be fired when a row is double clicked on.
     */
    Scrolltable.prototype.onDoubleClick = function(callback)
    {
        var rows = this.getRows();
        rows.forEach(function(row)
        {
            row.ondblclick = callback;
        });
    };

    return Scrolltable;
});
