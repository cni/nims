
// Parse the dicom file from the file content and overwrite
// the patient name tag with spaces in-place in the buffer
function redactIdentityInformation(fileContent) {
    var dataView = new DataView(fileContent);
    var dcmFile = parseFile(fileContent);

    // Overwrite Patient name with spaces
    var patientNameTag = dcmdict["PatientsName"];
    var patientNameElement = dcmFile.get_element(patientNameTag);
    if (patientNameElement) {
        var patientNameLength = patientNameElement.vl;
        var offsetName = patientNameElement.offset;

        for (var i = 0; i < patientNameLength; i++) {
            dataView.setUint8(offsetName + 8 + i, 0x20);
        }
    }

    // Set the patient birth day always to the 15th of the month
    var patientBirthTag = dcmdict["PatientsBirthDate"];
    var patientBirthElement = dcmFile.get_element(patientBirthTag);
    if (patientBirthElement) {
        var patientBirthDateLength = patientBirthElement.vl;
        var offsetBirth = patientBirthElement.offset;

        if (patientBirthDateLength == 8) {
            dataView.setUint8(offsetBirth + 8 + 6, 0x31);
            dataView.setUint8(offsetBirth + 8 + 7, 0x35);
        }
    }
}

function parseFile(fileContent){
	var buffer = new Uint8Array(fileContent);
    var dcmparser = new DicomParser(buffer);
    var file = dcmparser.parse_file();

    return file;
}

var files_to_upload = {};
var id_generator = 0;
var fileMap = {};
var totalFilesSize = 0;

var MAX_UPLOAD_SIZE = 3 * 1024 * 1024 * 1024;

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
         // Disable upload button while the upload is running
         $("input[type=submit]").attr("disabled", "disabled");
         $("input[type=submit]").addClass("lightColor");
         disableDnd();
         console.time("uploadTimer");
         $("#warning").addClass('hide');

         var upload_list = [];

         // The first step is to call startUpload for each series
         async.each(Object.keys(files_to_upload), function(key, callback) {
             var seriesId = files_to_upload[key].id;

             if ($('#checkbox_' + seriesId).is(":checked")) {
                 startUpload(key, callback);
                 //Error_checked: Upload list tiene los elementos que hemos marcado en el checked
                 upload_list = upload_list.concat(files_to_upload[key]);
             }  else {
                 callback();
             }
         }, function(err) {
             // This is called when all the startUpload calls are done
             if (err) {
                 console.log("Start uploads error:", err);
                 return;
             }

             // Upload all the files, 3 at once
             async.eachLimit(upload_list, 3, doUpload, function(err) {
                // Finished uploading all the files from every series

                // Call end upload for each series
                async.each(Object.keys(files_to_upload), endUpload, function(err) {
                    console.timeEnd('uploadTimer');
                });
             });
         });
	 }
});

function startUpload(key, callback) {
    $.ajax('upload/start_upload', {
        cache: false,
        data: new FormData(),
        contentType: false,
        processData: false,
        type: 'POST' })
    .done(function(data) {
        var response = JSON.parse(data);

        files_to_upload[key].upload_id = response.upload_id;
        files_to_upload[key].uploaded = 0;
        updateStatus(key, response);

        if (response.status == true) {
            callback();
        } else {
            callback(response.message);
        }
    }).fail( function(data){
        var response = JSON.parse(data);
        updateStatus(key, response);
        callback(response.message);
    });
}

function doUpload(file, callback) {
    var key = file.Key;

    // File is open, read the content
    var fileReader = new FileReader();
    fileReader.onload = function(evt){
        // Got the content
        var content = evt.target.result;
        redactIdentityInformation(content);
        var blob = new Blob([content]);

        // Upload this file to the server
        var data = new FormData();
        data.append('file', blob, file.name);
        data.append('upload_id', files_to_upload[key].upload_id);

        $.ajax('upload/upload_file', {
            data: data,
            cache: false,
            contentType: false,
            processData: false,
            type: 'POST' })
        .done( function(data){
            var response = JSON.parse(data);

            if (response.status == true) {
                // File was successfully uploaded
                files_to_upload[key].uploaded += 1;
                updateStatus(key, response);
                callback();
            } else {
                updateStatus(key, response);
                callback(response.message);
            }
        })
        .fail( function(data){
            updateStatus(key, {'message' : 'File upload failed'});
            callback('File upload failed');
        });
    }

    fileReader.readAsArrayBuffer(file);
}

function endUpload(key, callback) {
    var data = {};
    var series = files_to_upload[key];
    var upload_id = files_to_upload[key].upload_id;

    if ($('#checkbox_' + files_to_upload[key].id).length) {
        // If the series was not selected for upload, ignore it
        callback();
        return;
    }

    data['SeriesInstanceUID'] = series.SeriesInstanceUID;
    data['GroupValue'] = $('#group_value').val();
    data['Notes'] = $('#notes_' + series.id).val();
    data['AcquisitionNumber'] = series.AcquisitionNumber;
    data['upload_id'] = upload_id;

    $.post( "upload/end_upload", data)
        .done(function(data) {
            var response = JSON.parse(data);
            updateStatus(key, response);
            callback();
        })
        .fail( function(data){
            var response = JSON.parse(data);
            updateStatus(key, response);
            callback(response.message);
        });
}

// Add a file to the bottom list of file in the page
function addFileToList(file) {
    //Append to the list of FileObject to upload
    if (!files_to_upload[file.Key]){
        files_to_upload[file.Key] = [];

        //Make visible the table
        $('#table_scrollable').removeClass('hide');

        adjustImagesInAcquisition(file);

        // Add our generatered id to the file object
        var id = '_' + (id_generator++);
        files_to_upload[file.Key].id = id;
        files_to_upload[file.Key].totalSize = 0;
        files_to_upload[file.Key].StudyID = file.StudyID;
        files_to_upload[file.Key].SeriesNumber = file.SeriesNumber;
        files_to_upload[file.Key].AcquisitionNumber = file.AcquisitionNumber;
        files_to_upload[file.Key].SeriesInstanceUID = file.SeriesInstanceUID;
        files_to_upload[file.Key].ImagesInAcquisition = file.ImagesInAcquisition;

        var year = file.AcquisitionDate.substring(0, 4);
        var month = file.AcquisitionDate.substring(4, 6);
        var day = file.AcquisitionDate.substring(6, 8);

        $('#file_list_header').removeClass('hide');
        var output = [];
        output.push('<tr id="', id, '" style="text-align:center"> \
                        <td>', year, '-',  month, '-', day , '</td> \
                        <td><strong>', file.StudyID , '</strong></td> \
                        <td>', file.SeriesNumber, '.', file.AcquisitionNumber || 'n/a', '</td> \
                        <td size="200">', file.SeriesDescription, '</td> \
                        <td id="count_', id, '">', '</td> \
                        <td id="size_', id, '">', '</td> \
                        <td><input id="notes_', id,'" type="textbox" style  ="width:90%">', '</td> \
                        <td class="status"><input id="checkbox_', id, '" type="checkbox" checked="checked" ></input>',  '</td> \
                    </tr>');

        $('#file_list').append(output.join(''));
        var key = file.Key;

        // Set a timer to upload the status every 1s
        files_to_upload[key].timer = setInterval(updateFilesSubmitted.bind(this, key), 400);

        // Update the status the 1st time
        updateFilesSubmitted(key);
    }

    if (fileMap[file.name] == true) {
        // Ignoring duplicate file
        return;
    } else {
        // File is not already listed in the page
        fileMap[file.name] = true;
        file.id = files_to_upload[file.Key].id;
        files_to_upload[file.Key].push(file);

        files_to_upload[file.Key].totalSize += file.size;

        // If last file, update the page immediately
        if (files_to_upload[file.Key].length >= files_to_upload[file.Key].ImagesInAcquisition) {
            updateFilesSubmitted(file.Key);
        }
    }
}

function updateFilesSubmitted(key) {
    if (!files_to_upload[key]) {
        // The series has already been cleared
        return;
    }

    var imagesInAcquisition = files_to_upload[key].ImagesInAcquisition;
    var id = files_to_upload[key].id;
    var imagesSubmitted = files_to_upload[key].length;

    if (!imagesInAcquisition) {
        $('#count_' + id).html("<b>" + imagesSubmitted + "</b>");
    } else if (imagesSubmitted < imagesInAcquisition) {
        $('#count_' + id).html("<b style='color:red;'>" + imagesSubmitted + "</b>" +
        '/' + imagesInAcquisition);
    } else {
        // All the files for the series have been added
        $('#count_' + id).html("<b>" + imagesSubmitted + "</b>" + '/' +
            imagesInAcquisition);

        clearInterval(files_to_upload[key].timer);
    }


    $('#size_' + id).html(humanFileSize(files_to_upload[key].totalSize));
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

function updateStatus(key, result) {
    var totalFiles = files_to_upload[key].length;
    var uploaded = files_to_upload[key].uploaded;
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

    $('#' + id + ' td:last').html(uploaded + '/' + totalFiles + ' ' + (result.message || ''));
}

function clearFileList() {
    if (pendingDirectories != 0) {
        //There are fileEntry still on process so we have to reload to abort
        location.reload();
        return;
    }

    // Clear all the pending timers
    $.each(Object.keys(files_to_upload), function(idx, key) {
        clearInterval(files_to_upload[key].timer);
    });

    files_to_upload = {};
    fileMap = {};
    totalFilesSize = 0;
    $('#file_list').html('');
    $('#file_list_ignored').html('');
    $('#file_list_header').addClass('hide');
    $('#file_header_ignored').addClass('hide');
    $('#result_error').addClass('hide');
    $('#bannerjs-emptyfields').addClass('hide');
    $("input[type=submit]").removeAttr("disabled");
    $("input[type=submit]").removeClass("lightColor");
    $("#warning").addClass('hide');
    $('#totalSize').addClass('hide');
    enableDnd();
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
var pendingDirectories = 0;

function handleDnDSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();
    pendingDirectories = evt.originalEvent.dataTransfer.items.length;

    //Disable upload button while the DnD processing
    $("input[type=submit]").attr("disabled", "disabled");
    $("input[type=submit]").addClass("lightColor");

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

            // Now process each file sequentially
            async.mapSeries(fileList, openFile, function(err, resultList) {
                //Decrement pending every time we are done processin files in a
                //directory
                --pendingDirectories;
                if (pendingDirectories == 0) {

                    var missingFiles = false;

                    //Add warning sign in case slices missing
                    $.each(Object.keys(files_to_upload), function(idx, key) {
                        if (files_to_upload[key].ImagesInAcquisition
                                && files_to_upload[key].length < files_to_upload[key].ImagesInAcquisition) {
                            missingFiles = true;
                        }
                    });

                    if (missingFiles) {
                        $('#warning').removeClass('hide');
                    } else {
                        $('#warning').addClass('hide');
                    }

                    //Enable upload button while the submision
                    $("input[type=submit]").removeAttr("disabled");
                    $("input[type=submit]").removeClass("lightColor");
                }
            });
        });
    });
}

function openFile(fileEntry, callback) {

    // First open the file
    fileEntry.file(function(item) {

        // File is open, read the content
        incrementFileSize(item.size);
        if (totalFilesSize > MAX_UPLOAD_SIZE) {
            $('#bannerjs-emptyfields').removeClass('hide');
            $('#bannerjs-emptyfields').html("Reached the maximum total file size");
            callback('Reached maximum size', item);
        } else {
            // File is open, read the content
            processFile(item, callback);
        }

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
        fileList.push(entry);
    } else if (entry.isDirectory) {
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

    //Read and parse each selected file
    $.each(files, function(idx, file) {
        incrementFileSize(file.size);
        if (totalFilesSize >= MAX_UPLOAD_SIZE) {
            $('#bannerjs-emptyfields').removeClass('hide');
            $('#bannerjs-emptyfields').html("Reached the maximum total file size");
            return;
        } else {
            processFile(file, function() {
                //Done
            });
        }
    });
}

$('#files').on('change', handleFileInputSelect);

// Setup the dnd listeners.

function enableDnd() {
    $('#drop_zone').on('dragenter', handleDragEnter);
    $('#drop_zone').on('dragover', handleDragOver);
    $('#drop_zone').on('dragleave', handleDragLeave);
    $('#drop_zone').on('drop', handleDnDSelect);
    $('#drop_zone').on('click', loadinput);
}

function disableDnd() {
    $('#drop_zone').off('dragenter');
    $('#drop_zone').off('dragover');
    $('#drop_zone').off('dragleave');
    $('#drop_zone').off('drop');
    $('#drop_zone').off('click');

    $('#drop_zone').on('dragenter', function(evt) {
            evt.stopPropagation();
            evt.preventDefault();
    });
    $('#drop_zone').on('dragover', function(evt) {
        evt.stopPropagation();
        evt.preventDefault();
    });
    $('#drop_zone').on('dragleave', function(evt) {
        evt.stopPropagation();
        evt.preventDefault();
    });
    $('#drop_zone').on('drop', function(evt) {
        evt.stopPropagation();
        evt.preventDefault();
    });
}

enableDnd();

// Utils
function incrementFileSize(bytes) {
    totalFilesSize += bytes;
}

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
