require(['scrolltab2', 'scrolltab_mixins'], function (scrolltab, mixins) {
    mixins.asSortable.call(scrolltab.Scrolltable.prototype);
    mixins.asLoadable.call(scrolltab.Scrolltable.prototype);
    mixins.asSelectable.call(scrolltab.Scrolltable.prototype);
    var el = new scrolltab.Scrolltable("test", "HI");
    el.enableHeaderClickSorting();
    el.enableClickSelection();
    el._body.style.height = "80px";
});
