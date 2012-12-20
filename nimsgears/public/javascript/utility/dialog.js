define([], function ()
{
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

    /* Render a jquery dialog for a given dialog (popup), type (string of
     * type), and load a particular URL into the dialog's iframe */
    var showDialog = function(popup, type, url)
    {
        var iframe = popup.find('iframe');
        // binds an event to show the popup when it is DONE loading
        iframe.bind('load.show', function() {
            // width and height of the iframe are computed and bound as minimum
            // width and height on the popup
            var width = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).width();
            var height = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).height();
            popup.dialog({
                resizable:false,
                modal:true,
                closeOnEscape:true,
                minWidth:width,
                minHeight:height + 10
            });
            //popup.width(width);
            //popup.height(height);
            // unbind the show event (we don't want to reload the popup every
            // time it reloads, since we occasionally reload while the window
            // is still open
            iframe.unbind('load.show');
        });
        // directs to the relevant URL
        iframe.attr('src', url);
        popup.attr('title', "Edit " + type);
    };

    /* Handles size adjustments when dialog boxes are reloaded while still
     * open. */
    var bindSizeChange = function(popup) {
        var iframe = popup.find('iframe');
        iframe.bind('load.sizechange', function() {
            var width = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).width();
            var height = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).height();
            iframe.width(width);
            iframe.height(height);
        });
    };

    return {
        showDialog: showDialog,
        bindSizeChange: bindSizeChange,
    };
});
