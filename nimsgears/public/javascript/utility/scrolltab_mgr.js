define(['utility/scrolltab'], function (Scrolltable)
{
    var table_with_focus;
    var tables_by_id = new Array(); // dictionary

    var setFocus = function(table_key)
    {
        set_to_table = tables_by_id[table_key];
        if (set_to_table)
        {
            if (table_with_focus)
            {
                table_with_focus.setFocus(false);
            }
            table_with_focus = set_to_table;
            table_with_focus.setFocus(true);
        }
    };

    var setTableHeights = function ()
    {
        var vp_size = viewport();
        var table_height = vp_size.height - 380;
        table_height = table_height > 200 ? table_height : 200;
        for (var key in tables_by_id)
        {
            if (tables_by_id.hasOwnProperty(key))
            {
                tables_by_id[key].getBody().closest('.scrolltable_body').height(table_height);
            }
        }
    };

    var viewport = function ()
    {
        var e = window;
        a = 'inner';
        if ( !( 'innerWidth' in window ) )
        {
            a = 'client';
            e = document.documentElement || document.body;
        }
        return { width : e[ a+'Width' ] , height : e[ a+'Height' ] }
    }

    var getById = function(id)
    {
        return tables_by_id[id];
    };

    var getTableWithFocus = function()
    {
        return tables_by_id[table_with_focus];
    };

    var init = function()
    {
        var scrolltable;
        all_scrolltables = $(".scrolltable");
        all_scrolltables.each(function()
        {
            if (this.hasAttribute('id'))
            {
                scrolltable = Scrolltable($(this));
                scrolltable.init();
                scrolltable.onSelect(tableSelected);
                tables_by_id[this.getAttribute('id')] = scrolltable;
            }
        });
    };

    var autoSetTableHeights = function ()
    {
        $(window).resize(function() { setTableHeights(); });
    };

    var resortAll = function()
    {
        for (var key in tables_by_id)
        {
            if (tables_by_id.hasOwnProperty(key))
            {
                tables_by_id[key].resort();
            }
        }
    };

    var setClickEventsAll = function()
    {
        for (var key in tables_by_id)
        {
            if (tables_by_id.hasOwnProperty(key))
            {
                tables_by_id[key].setClickEvents();
            }
        }
    };

    var tableSelected = function(event)
    {
        if (table_with_focus)
        {
            table_with_focus.setFocus(false);
        }
        table_with_focus = getById(event.table_key);
        table_with_focus.setFocus(true);
    };

    var getFocus = function()
    {
        return table_with_focus;
    };

    return {
        init: init,
        resortAll: resortAll,
        getById: getById,
        getFocus: getFocus,
        setFocus: setFocus,
        setTableHeights: setTableHeights,
        setClickEventsAll: setClickEventsAll,
        autoSetTableHeights: autoSetTableHeights
    };
});
