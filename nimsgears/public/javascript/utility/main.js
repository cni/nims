require(['scrolltab/scrolltab', 'scrolltab/mixins/sortable', 'scrolltab/mixins/loadable', 'scrolltab/mixins/selectable', 'scrolltab/mixins/kbsupport', 'scrolltab/manager'], function (Scrolltable, asSortable, asLoadable, asSelectable, withKbSupport, Drilldown) {
    // mixins for functionality
    asSortable.call(Scrolltable.prototype);
    asLoadable.call(Scrolltable.prototype);
    withKbSupport.call(Scrolltable.prototype);

    // table creation and set up
    var el = new Scrolltable("test", "HI");
    var el2 = new Scrolltable("test1", "HI");
    el.enableHeaderClickSorting();
    el2.enableHeaderClickSorting();
    el.enableMouseSelection();
    el2.enableMouseSelection();
    el.enableKeyboardSelection();
    el2.enableKeyboardSelection();
    el._body.style.height = "120px";
    el2._body.style.height = "120px";
    var blah = new Drilldown([el, el2]);
    blah.enableKeyboardNavigation();
});
