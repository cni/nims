
// Parse the dicom file from the file content and overwrite
// the patient name tag with spaces in-place in the buffer
function redactPatientName(fileContent) {
    var dataView = new DataView(fileContent);
    var dcmFile = parseFile(fileContent);

    var patientNameTag = dcmdict["PatientsName"];
    var patientNameElement = dcmFile.get_element(patientNameTag);
    var patientNameLength = patientNameElement.vl;
    var offset = patientNameElement.offset;

    for (var i = 0; i < patientNameLength; i++) {
        dataView.setUint8(offset + 8 + i, 0x20);
    }
}

function parseFile(fileContent){
	var buffer = new Uint8Array(fileContent);
    var dcmparser = new DicomParser(buffer);
    var file = dcmparser.parse_file();
    //console.log('File: ', file);

    return file;
}

var files_to_upload = {};
var id_generator = 0;
var fileList = []

$('#submit_form').on('click', function(evt) {
     evt.stopPropagation();
     evt.preventDefault();

     $('#bannerjs-emptyfields').addClass('hide');

     if (!$('#group_value').val() ){
         $('#bannerjs-emptyfields').removeClass('hide');
         $('#bannerjs-emptyfields').html("Fields in the form should be completed");
     } else if (isFilesToUploadEmpty()) {
         $('#bannerjs-emptyfields').removeClass('hide');
         $('#bannerjs-emptyfields').html("Please select some files to upload");
     } else {
         //Disable upload button while the submision
         $("input[type=submit]").attr("disabled", "disabled");

         // Also pass a map (filename, Id) to the server
         $.each(Object.keys(files_to_upload), function(i, key) {
             startUpload(key);
         });
	 }
});


function startUpload(key) {
    $.ajax('upload/start_upload', {
        cache: false,
        data: new FormData(),
        contentType: false,
        processData: false,
        type: 'POST' })
    .done(function(data) {
        var response = JSON.parse(data);
        console.log("Received start upload response: ", response);

        if (response.status == true) {
            // Start uploading the 1st file
            doUpload(key, 0, response.upload_id);
        }

        updateStatus(key, 0, response);
    }).fail( function(data){
        var response = JSON.parse(data);
        updateStatus(key, 0, response);
    });
}

function doUpload(key, idx, upload_id) {
    var file = files_to_upload[key][idx];

    // File is open, read the content
    var fileReader = new FileReader();
    fileReader.onload = function(evt){
        // Got the content
        var content = evt.target.result;
        redactPatientName(content);
        var blob = new Blob([content]);

        // Upload this file to the server
        var data = new FormData();
        data.append('file', blob, file.name);
        data.append('upload_id', upload_id);

        $.ajax('upload/upload_file', {
            data: data,
            cache: false,
            contentType: false,
            processData: false,
            type: 'POST' })
        .done( function(data){
            var response = JSON.parse(data);
            if (response.status == true) {

                idx += 1;
                if (idx == files_to_upload[key].length) {
                    console.log("Finished uploading files for key", key);
                    endUpload(key, upload_id);
                } else {
                    doUpload(key, idx, upload_id);
                }
            }

            updateStatus(key, idx, response);
        })
        .fail( function(data){
            updateStatus(key, idx, {'message' : 'File upload failed'});
        });
    }

    fileReader.readAsArrayBuffer(file);
}

function endUpload(key, upload_id) {
    var data = {};
    var series = files_to_upload[key];
    data['SeriesInstanceUID'] = series.SeriesInstanceUID;
    data['GroupValue'] = $('#group_value').val();
    data['Notes'] = $('#notes_' + series.id).val();
    data['upload_id'] = upload_id;

    $.post( "upload/end_upload", data)
        .done(function(data) {
            var response = JSON.parse(data);
            console.log("Received end upload response: ", response);
            updateStatus(key, files_to_upload[key].length, response);
        })
        .fail( function(data){
            var response = JSON.parse(data);
            updateStatus(key, files_to_upload[key].length, response);
        });
}

// Add a file to the bottom list of file in the page
function addFileToList(file) {
    //Append to the list of FileObject to upload
    if (!files_to_upload[file.Key]){
        files_to_upload[file.Key] = [];

        //Make visible the table
        $('#table_scrollable').removeClass('hide');

        // Add our generatered id to the file object
        var id = '_' + (id_generator++);
        files_to_upload[file.Key].id = id;
        files_to_upload[file.Key].totalSize = 0;
        files_to_upload[file.Key].StudyID = file.StudyID;
        files_to_upload[file.Key].SeriesNumber = file.SeriesNumber;
        files_to_upload[file.Key].AcquisitionNumber = file.AcquisitionNumber;
        files_to_upload[file.Key].SeriesInstanceUID = file.SeriesInstanceUID;

        var year = file.AcquisitionDate.substring(0, 4);
        var month = file.AcquisitionDate.substring(4, 6);
        var day = file.AcquisitionDate.substring(6, 8);

        $('#file_list_header').removeClass('hide');
        var output = [];
        output.push('<tr id="', id, '" style="text-align:center"> \
                        <td>', year + '-' + month + '-' + day , '</td> \
                        <td><strong>', file.StudyID , '</strong></td> \
                        <td>', file.SeriesNumber + '.' + file.AcquisitionNumber || 'n/a', '</td> \
                        <td size="200">', file.SeriesDescription, '</td> \
                        <td id="count_', id, '">', '</td> \
                        <td id="size_', id, '">', '</td> \
                        <td><input id="notes_', id,'" type="textbox" style  ="width:90%">', '</td> \
                        <td class="status"><input id="checkbox_', id, '" type="checkbox" checked="checked" ></input>',  '</td> \
                    </tr>');

        $('#file_list').append(output.join(''));
    }

    if ($.inArray(file.name, fileList) == -1) {
        // File is not already listed in the page
        fileList.push(file.name);
        file.id = files_to_upload[file.Key].id;
        files_to_upload[file.Key].push(file);
    } else {
        // Ignoring duplicate file
        return;
    }

    adjustImagesInAcquisition(file);

    var imagesSubmitted = files_to_upload[file.Key].length;

    if (imagesSubmitted == file.ImagesInAcquisition) {
        $('#count_' + file.id).html("<b>" + imagesSubmitted + "</b>" + '/' +
            file.ImagesInAcquisition);
    } else {
        $('#count_' + file.id).html("<b style='color:red;'>" + imagesSubmitted + "</b>" +
            '/' + file.ImagesInAcquisition);
    }

    files_to_upload[file.Key].totalSize += file.size;
    $('#size_' + file.id).html(humanFileSize(files_to_upload[file.Key].totalSize));
}

// Perform a more precise evaluation of the total number
// of images in the serie
function adjustImagesInAcquisition(file) {
    if (file.ImagesInAcquisition == undefined) {
        file.ImagesInAcquisition = 0;
    }

    if (file.SlicesPerVolume == undefined) {
        file.SlicesPerVolume = 1;
    }

    if (file.NumberOfTemporalPositions == undefined) {
        file.NumberOfTemporalPositions = file.ImagesInAcquisition / file.SlicesPerVolume;
    }

    if (file.SlicesPerVolume == file.ImagesInAcquisition) {
        file.ImagesInAcquisition = file.SlicesPerVolume * file.NumberOfTemporalPositions;
    }
}

function addToIgnoredFilesList(file) {
    var output = [];
    $('#file_header_ignored').removeClass('hide');

    output.push('<tr style="text-align:center; color:#bbb;"> \
                     <td><strong>', file.name, '</strong></td> \
                     <td>', file.type || "n/a", '</td> \
                     <td>', file.size, '</td> \
                     <td class="status">', file.status, '</td> \
                 </tr>');

    $('#file_list_ignored').append(output.join(''));
}

function isFilesToUploadEmpty() {
    var isEmpty = true;

    $.each(Object.keys(files_to_upload), function(i, key) {
        if (files_to_upload[key].length > 0) {
            isEmpty = false;
        }
    });

    return isEmpty;
}

function updateStatus(key, uploaded, result) {
    //console.log('Updating file status for ', fileResult.filename);
    var totalFiles = files_to_upload[key].length;
    var id = files_to_upload[key].id;

    if (result.status == true) {
        // File was uploaded and processed correctly
        if (uploaded == totalFiles) {
            $('#' + id).addClass('complete');
        } else {
            $('#' + id).addClass('ok');
        }
    } else {
        $('#' + id).addClass('error');
    }

    $('#' + id + ' td:last').html(uploaded + '/' + totalFiles + ' ' + result.message);
}

function clearFileList() {
    files_to_upload = {};
    $('#file_list').html('');
    $('#file_list_ignored').html('');
    $('#file_list_header').addClass('hide');
    $('#file_header_ignored').addClass('hide');
    $('#result_error').addClass('hide');
    $('#bannerjs-emptyfields').addClass('hide');
    $("input[type=submit]").removeAttr("disabled");
}

$('#clear_form').on('click', clearFileList);

$("input:checkbox").live('click', function(){
    var checkbox_id = $(this).attr('id');
    if ( !$('#' + checkbox_id).is(":checked")){
        $('#' + checkbox_id).removeAttr('checked');
    }else{
         $('#' + checkbox_id).attr("checked","checked");
    }
});

////////////////////////////////////////////////////////////////
// Drag & Drop functions
////////////////////////////////////////////////////////////////

function handleDnDSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();
    var pendingDirectories = evt.originalEvent.dataTransfer.items.length;
    //Disable upload button while the DnD processing
    $("input[type=submit]").attr("disabled", "disabled");

    $.each(evt.originalEvent.dataTransfer.items, function(idx, item){
        var entry;
        if (item.getAsEntry) { //Standard HTML5 API
            entry = item.getAsEntry();
        } else if(item.webkitGetAsEntry) { //Webkit implementation of HTML5 API
            entry = item.webkitGetAsEntry();
        }

        var fileList = [];
        fileList.pendingOps = 0;
        traverseFileTree(entry, fileList, function() {
            console.log("Done traversing file tree for ", entry.name, ' Found files: ', fileList.length);

            // Now process each file sequentially
            async.mapSeries(fileList, openFile, function(err, resultList) {
                //Decrement pending every time we are done processin files in a
                //directory
                --pendingDirectories;
                if (pendingDirectories == 0) {
                    //Enable upload button while the submision
                    $("input[type=submit]").removeAttr("disabled");
                }
            });
        });
    });
}

function openFile(fileEntry, callback) {
//    console.log('Opening file:', fileEntry.fullPath);

    // First open the file
    fileEntry.file(function(item) {
        // File is open, read the content
        processFile(item, callback);

    }, function(item) {
        // Failed to open the file
        item.status = "Could not open file";
        addToIgnoredFilesList(item);
        callback(null, item)
    });
}

function processFile(file, callback) {
    if (file.name.substring(0,1) == '.') {
        // Ignoring hidden files
        callback(null, file);
        return;
    }

    var fileReader = new FileReader();
    fileReader.onload = function(evt){
        // console.log('Finished to read content of file:', file.name);

        var fileContent = evt.target.result;
        var filelength = file.name.length;

        try {

            var dcmFile = parseFile(fileContent);
            file.status = "Valid File";
            file.StudyID = dcmFile.StudyID;
            file.InstanceNumber = dcmFile.InstanceNumber;
            file.SeriesInstanceUID = dcmFile.SeriesInstanceUID;
            file.SeriesDescription = dcmFile.SeriesDescription;
            file.AcquisitionNumber = dcmFile.AcquisitionNumber;
            file.SeriesNumber = dcmFile.SeriesNumber;
            file.ImagesInAcquisition = dcmFile.ImagesInAcquisition;
            file.AcquisitionDate = dcmFile.AcquisitionDate;
            file.ImagesInAcquisition = dcmFile.ImagesInAcquisition;
            file.NumberOfTemporalPositions = dcmFile.NumberOfTemporalPositions;

            //Retrieve SlicesPerVolume by tag:
            var SLICES_PER_VOLUME_TAG = 0x0021104F;
            slicesPerVolume_le0 = dcmFile.get_element(SLICES_PER_VOLUME_TAG).data[0];
            slicesPerVolume_le1 = 256 * dcmFile.get_element(SLICES_PER_VOLUME_TAG).data[1];
            file.SlicesPerVolume = slicesPerVolume_le0 + slicesPerVolume_le1;
            //console.log('slices per volume (using get_elemet function): ', file.SlicesPerVolume);

            file.Key = ['key', file.StudyID, file.SeriesNumber, file.AcquisitionNumber,
                                file.SeriesInstanceUID].join('-');

            // Add the file to table of files in the page
            addFileToList(file);
            callback(null, file);

        } catch (err) {
            console.log('Error parsing dicom file:', err, 'file Name: ', file.name);
            console.dir(err);
            // Could not parse the dicom file
            file.status = "Not valid";

            addToIgnoredFilesList(file);
            callback(null, file);
        }
    }
    fileReader.onerror = function(evt){
        console.log("Error reading file ", file.name, ':', evt.target.error);

        file.status = "Cannot read file";
        addToIgnoredFilesList(file);
        callback(null, file);
    }

    fileReader.readAsArrayBuffer(file);
}

function traverseFileTree(entry, fileList, traverseCallback) {
    if (entry.isFile) {
        // console.log("File:", entry.fullPath);
        fileList.push(entry);
    } else if (entry.isDirectory) {
        // console.log("Dir:", entry.fullPath);
        ++fileList.pendingOps;
        var dirReader = entry.createReader();
        dirReader.readEntries(function(entries) {
            for (var idx = 0; idx < entries.length; idx++) {
                traverseFileTree(entries[idx], fileList, traverseCallback);
            }

            if (--fileList.pendingOps == 0) {
                // All the async operations have completed
                traverseCallback();
            }
        });
    }

    if (fileList.pendingOps == 0) {
        traverseCallback();
    }
}

function handleDragEnter(evt) {
    $("#drop_zone").addClass("over");
}

function handleDragOver(evt) {
    evt.stopPropagation();
    evt.preventDefault();
    evt.originalEvent.dataTransfer.dropEffect = 'copy'; // Explicitly show this is a copy.
}

function handleDragLeave(evt) {
    $("#drop_zone").removeClass("over");
}

////////////////////////////////////////////////////////////////
// File input button functions
////////////////////////////////////////////////////////////////

function loadinput(evt){
    evt.stopPropagation();
    evt.preventDefault();
    $('#files').click();
}

function handleFileInputSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    var files = evt.target.files;
    console.log('Handle File Input select:', files);

	// Read and parse each selected file
    $.each(files, function(idx, file) {
		processFile(file, function() {
		    // Done
		});
    });
}

$('#files').on('change', handleFileInputSelect);

// Setup the dnd listeners.
$('#drop_zone').on('dragenter', handleDragEnter);
$('#drop_zone').on('dragover', handleDragOver);
$('#drop_zone').on('dragleave', handleDragLeave);
$('#drop_zone').on('drop', handleDnDSelect);
$('#drop_zone').on('click', loadinput);




// Utils

function humanFileSize(bytes) {
    if (bytes < 1024) {
        return bytes + ' B';
    }

    var units = ['Kb','Mb','Gb'];
    var u = -1;
    do {
        bytes /= 1024;
        ++u;
    } while(bytes >= 1024);
    return bytes.toFixed(1) + ' ' + units[u];
};
