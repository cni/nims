require(['scrolltab/scrolltab', 'scrolltab/mixins/sortable', 'scrolltab/mixins/loadable', 'scrolltab/mixins/selectable', 'scrolltab/mixins/kbsupport', 'scrolltab/manager', 'tablednd'],
function (Scrolltable, asSortable, asLoadable, asSelectable, withKbSupport, Drilldown, TableDragAndDrop) {
    // mixins for functionality
    asSortable.call(Scrolltable.prototype);
    asLoadable.call(Scrolltable.prototype);
    withKbSupport.call(Scrolltable.prototype);
    var rand = function() { return Math.floor((Math.random()*10)+1); };
    var blah = function(table, selected_rows, populateNextTableFn)
    {
        console.log('wat' + rand());
        if (selected_rows.length == 1)
        {
            populateNextTableFn(table, {'data':[
                ['ugh' + rand(), 'what'], ['fuck', 'shit' + rand()], ['omgz', 'absdifjasd'],
                ['ugh' + rand(), 'what'], ['fuck', 'shit' + rand()], ['omgz', 'absdifjasd'],
                ]});
        }
        else
        {
            populateNextTableFn(table, []);
        }
    };
    var populators = [blah, blah, blah];
    // table creation and set up
    var tables = [new Scrolltable("test", "HI1"), new Scrolltable("test1", "HI2"), new Scrolltable("test2", "HI3")];
    tables.forEach(function (table)
    {
        table.init_sortable();
        table.init_loadable();
        table.init_kbsupport();
        table._body.style.height = "120px";
    });
    var blah = new Drilldown(tables, populators);
    blah.enableKeyboardNavigation();
    tables.forEach(function(table)
    {
        TableDragAndDrop.setupDraggable($(table._body.getElementsByTagName("table")[0]));
    });
    console.log('fuck');
});
