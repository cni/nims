define(['./scrolltab', './mixins/sortable', './mixins/loadable', './mixins/selectable', './mixins/kbsupport'],
function (Scrolltable, asSortable, asLoadable, asSelectable, withKbSupport) {
    // mixins for functionality
    asSortable.call(Scrolltable.prototype);
    asLoadable.call(Scrolltable.prototype);
    withKbSupport.call(Scrolltable.prototype);

    function Drilldown(table_id, title)
    {
        Scrolltable.call(this, table_id, title);
        this.init_drilldown();
    };

    Drilldown.prototype = new Scrolltable();

    Drilldown.prototype.init_drilldown = function()
    {
        this.init_sortable();
        this.init_loadable();
        this.init_kbsupport();
    };

    return Drilldown;
});
