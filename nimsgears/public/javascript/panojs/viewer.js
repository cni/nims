var scr = document.getElementsByTagName('script');
var scr_url = scr[scr.length-1].getAttribute("src");
var base_url = scr_url.substring(0,scr_url.lastIndexOf('/')) + '/images/';

PanoJS.MSG_BEYOND_MIN_ZOOM = null;
PanoJS.MSG_BEYOND_MAX_ZOOM = null;

function createViewer( viewer, dom_id, url, prefix, tile_size, w, h ) {
    if (viewer) return;

    var myPyramid = new ImgcnvPyramid(w, h, tile_size);

    var myProvider = new PanoJS.TileUrlProvider('','','');
    myProvider.assembleUrl = function(xIndex, yIndex, zoom) {
        return url + '/' + prefix + myPyramid.tile_filename( zoom, xIndex, yIndex );
    }

    viewer = new PanoJS(dom_id, {
        tileUrlProvider : myProvider,
        tileSize        : myPyramid.tilesize,
        maxZoom         : myPyramid.getMaxLevel(),
        imageWidth      : myPyramid.width,
        imageHeight     : myPyramid.height,
        staticBaseURL   : base_url,
        maximizeControl : false
    });

    Ext.EventManager.addListener( window, 'resize', callback(viewer, viewer.resize) );
    viewer.init();
    //viewer.maximizeView();
}

