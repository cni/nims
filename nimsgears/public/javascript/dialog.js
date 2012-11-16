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

    var showDialog = function(popup, ajax_data, url)
    {
        $.ajax({
            traditional: true,
            type: 'POST',
            url: url,
            dataType: "json",
            data: ajax_data,
            success: function(data)
            {
                if (data.success)
                {
                    var width = 'auto';
                    var height = 'auto';

                    // Do to all boxes
                    popup.find('p').text(data.name);
                    // Box specific modifications
                    switch (data.type)
                    {
                        case "experiment":
                            popup.attr('title', data.type + " " + ajax_data.exp_id);
                            break;
                        case "session":
                            popup.attr('title', data.type + " " + ajax_data.sess_id);
                            break;
                        case "epoch":
                            popup.attr('title', data.type + " " + ajax_data.epoch_id);
                            break;
                        case "dataset":
                            if (data.subtype == "pyramid")
                            {
                                var viewport_size = viewport();
                                width = viewport_size.width * .8;
                                height = viewport_size.height * .8;
                            }
                            popup.find('iframe').attr('src', data.url);
                            popup.find('iframe')[0].onload = function() {
                                popup.dialog({
                                    resizable:false,
                                    modal:true,
                                    focus:function(event, ui) { },
                                    closeOnEscape:true,
                                    width:width,
                                    minHeight:height,
                                    buttons: { },
                                });
                                popup.find('iframe')[0].onload = null;
                            };
                            $("#image_viewer").height(height);
                            $("#image_viewer").width(width);
                            popup.attr('title', data.type + " " + ajax_data.dataset_id);
                            break;
                    }
                    if (data.type != "dataset") {
                        popup.dialog({
                            resizable:false,
                            modal:true,
                            focus:function(event, ui) { },
                            closeOnEscape:true,
                            width:width,
                            minHeight:height,
                            buttons: { },
                        });
                    }
                }
            },
        });
    };

    return {
        showDialog: showDialog,
    };
});
