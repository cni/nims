define([], function ()
{
    var width_buffer = 25;
    var height_buffer = 25;

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

    /*
     * dialogSize
     * Compute size dialog should take given the iframes size.
     *
     * iframe - iframe object inside popup
     * type - optional name of type (handles special case)
     */
    var dialogSize = function(iframe, type)
    {
        var viewport_size = viewport();
        var max_width = viewport_size.width - width_buffer;
        var max_height = viewport_size.height - height_buffer;
        var width = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).width();
        var height = $(iframe[0].contentDocument.getElementsByTagName("html")[0]).height();
        if (width > max_width) width = max_width;
        if (height > max_height) height = max_height;
        // we handle a special case here - when the dataset loads and is
        // small, it means we're dealing with the pyramid rendering and
        // it has yet to finish loading, so we just expand it to full
        // width and height
        if (type == 'dataset' && (width < 26 || height < 26)) { width = max_width; height = max_height; };
        return { 'width': width, 'height': height };
    };

    /*
     * Render a jquery dialog for a given dialog (popup), type (string of
     * type), and load a particular URL into the dialog's iframe
     */
    var showDialog = function(popup, type, url)
    {
        var iframe = popup.find('iframe');
        // binds an event to show the popup when it is DONE loading
        iframe.bind('load.show', function() {
            iframe = popup.find('iframe');
            var dims = dialogSize(iframe, type);
            var width = dims.width;
            var height = dims.height;
            popup.dialog({
                resizable:false,
                modal:true,
                closeOnEscape:true,
                width:width,
                height:height,
                close: function() { $(this).dialog("destroy"); },
            });
            // unbind the show event (we don't want to reload the popup every
            // time it reloads, since we occasionally reload while the window
            // is still open
            iframe.unbind('load.show');
        });
        // directs to the relevant URL
        iframe.attr('src', url);
        var convert_type_string = type.charAt(0).toUpperCase() + type.slice(1);
        popup.attr('title', convert_type_string);
    };

    /*
     * Handles size adjustments when dialog boxes are reloaded while still
     * open.
     */
    var bindSizeChange = function(popup, type) {
        var iframe = popup.find('iframe');
        iframe.bind('load.sizechange', function() {
            iframe = popup.find('iframe');
            var dims = dialogSize(iframe, type);
            var width = dims.width;
            var height = dims.height;
            iframe.width(width);
            iframe.height(height);
            popup.width(width);
            popup.height(height);
        });
    };

    return {
        showDialog: showDialog,
        bindSizeChange: bindSizeChange,
    };
});
