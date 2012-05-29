require(['scrolltab/scrolltab', 'scrolltab/mixins/sortable', 'scrolltab/mixins/loadable', 'scrolltab/mixins/selectable'], function (Scrolltable, asSortable, asLoadable, asSelectable) {
    asSortable.call(Scrolltable.prototype);
    asLoadable.call(Scrolltable.prototype);
    asSelectable.call(Scrolltable.prototype);
    var el = new Scrolltable("test", "HI");
    el.enableHeaderClickSorting();
    el.enableSelection();
    el._body.style.height = "80px";
});
