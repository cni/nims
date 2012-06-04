define([], function()
{
    return function()
    {
        // Allows insertion of a loader div to be displayed when table is in
        // process of loading. Hides table content and shows loader div, then
        // redisplays table when stopLoading called.
        this.init_loadable = function()
        {
            this._loading_div;
        };

        this._getBodyTable = function()
        {
            return this._body.getElementsByTagName("table")[0];
        };

        this.setLoadingDiv = function(loading_div)
        {
            loading_div.hidden = true;
            var body_table = this._getBodyTable();
            this._body.insertBefore(loading_div, body_table);
            this._loading_div = loading_div;
        };

        this.startLoading = function()
        {
            var body_table = this._getBodyTable();
            body_table.hidden = true;
            this._loading_div.hidden = false;
        };

        this.stopLoading = function()
        {
            this._getBodyTable().hidden = false;
            this._loading_div.hidden = true;
        };
    };
});
