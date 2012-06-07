require(['scrolltab/drilldown', 'scrolltab/manager', 'tablednd'],
function (DrilldownTab, Drilldown, TableDragAndDrop) {
    // mixins for functionality
    var rand = function() { return Math.floor((Math.random()*10)+1); };
    var blah = function(table, selected_rows, populateNextTableFn)
    {
        console.log('wat' + rand());
        setTimeout(function() {
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
        }, 600);

    };
    var populators = [blah, blah, blah];
    // table creation and set up
    var tables = [new DrilldownTab("test", "HI1"), new DrilldownTab("test1", "HI2"), new DrilldownTab("test2", "HI3")];
    tables.forEach(function (table)
    {
        table._body.style.height = "120px";
    });
    var blah = new Drilldown(tables, populators);
    blah.enableKeyboardNavigation();
    tables.forEach(function(table)
    {
        TableDragAndDrop.setupDraggable($(table._body.getElementsByTagName("table")[0]));
    });
});
