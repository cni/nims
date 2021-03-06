define(['./scrolltab', './mixins/sortable', './mixins/loadable', './mixins/selectable', './mixins/kbsupport'],
function (Scrolltable, asSortable, asLoadable, asSelectable, withKbSupport) {
    // mixins for functionality - imbues the scrolltable with each given chunk
    // of functionality
    asSortable.call(Scrolltable.prototype); // sortable rows
    asLoadable.call(Scrolltable.prototype); // reloadable content
    withKbSupport.call(Scrolltable.prototype); // keyboard nav support

    /* Drilldown Constructor
     *
     * table_id - id of the table to convert into a drilldown table
     * title - string name you'd like placed at the top of the table
     */
    function Drilldown(table_id, title, sort_col, sort_dir)
    {
        sort_col = typeof sort_col !== 'undefined' ? sort_col : 0;
        sort_dir = typeof sort_dir !== 'undefined' ? sort_dir : 1;
        Scrolltable.call(this, table_id, title);
        this.init_drilldown(sort_col, sort_dir);
    };

    // Initialize parent type functionality
    Drilldown.prototype = new Scrolltable();

    /* init_drilldown
     * Initialize drilldown functionality (includes everything tacked on,
     * including sortable, loadable, and keyboard support.
     */
    Drilldown.prototype.init_drilldown = function(sort_col, sort_dir)
    {
        this.init_sortable(function(obj) { obj.synchronizeSelections(); }, sort_col, sort_dir);
        this.init_loadable();
        this.init_kbsupport();
    };

    return Drilldown;
});
