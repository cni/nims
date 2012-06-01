require(['scrolltab/scrolltab', 'scrolltab/mixins/sortable', 'scrolltab/mixins/loadable', 'scrolltab/mixins/selectable', 'scrolltab/mixins/kbsupport'], function (Scrolltable, asSortable, asLoadable, asSelectable, withKbSupport) {
    // mixins for functionality
    asSortable.call(Scrolltable.prototype);
    asLoadable.call(Scrolltable.prototype);
    withKbSupport.call(Scrolltable.prototype);

    // table creation and set up
    var el = new Scrolltable("test", "HI");
    el.enableHeaderClickSorting();
    el.enableMouseSelection();
    el.enableKeyboardSelection();
    el._body.style.height = "80px";
});
