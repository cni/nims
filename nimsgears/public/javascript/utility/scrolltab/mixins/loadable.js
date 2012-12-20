define([], function()
{
    return function()
    {
        /*
         * init_loadable
         * Allows insertion of a loader div to be displayed when table is in
         * process of loading. Hides table content and shows loader div, then
         * redisplays table when stopLoading called.
         */
        this.init_loadable = function()
        {
            this.timeout = 250; // ms
            this._loading_timeout;
            this._loading_div;
        };

        /*
         * _getBodyTable
         * Returns table holding the 'body' of the scrolltable (scrolltables
         * are built from 2 tables - a header and body table).
         */
        this._getBodyTable = function()
        {
            return this._body.getElementsByTagName("table")[0];
        };

        /*
         * setLoadingDiv
         * Set pointer to div that will be used for representing loading state.
         *
         * loading_div - div to be shown when loading occuring
         */
        this.setLoadingDiv = function(loading_div)
        {
            loading_div.hidden = true;
            var body_table = this._getBodyTable();
            this._body.insertBefore(loading_div, body_table);
            this._loading_div = loading_div;
        };

        /*
         * startLoading
         * Hide table body content and show loading div. Cease loading with
         * stopLoading.
         */
        this.startLoading = function()
        {
            if (this._loading_timeout)
            {
                clearTimeout(this._loading_timeout);
                this._loading_timeout = null;
            }
            var obj = this;
            this._loading_timeout = setTimeout(function()
            {
                var body_table = obj._getBodyTable();
                body_table.hidden = true;
                obj._loading_div.hidden = false;
            }, this.timeout);
        };

        /*
         * stopLoading
         * Hide the loading div and show the table body content.
         */
        this.stopLoading = function()
        {
            clearTimeout(this._loading_timeout);
            this._getBodyTable().hidden = false;
            this._loading_div.hidden = true;
        };
    };
});
