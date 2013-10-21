
function findOffset(data, seq) {
    var array = new Int8Array(data);

    for (var i = 0; i < (array.length - seq.length); i++) {
        var j;
        for (j = 0; j < seq.length; j++) {
            if (array[i+j] != seq[j]) {
                break;
            }
        }

        if (j == seq.length) {
            // We've reached the end of the seq array without break,
            // I have found a match
            return i;
        }
    }

    return -1;
}

function redactPatientName(fileContent, dcmFile) {
    var dataView = new DataView(fileContent);

    //Search for the sequence ( 0010 0010 PN ) that corresponds to the tag and initials of Patient Name
    offset = findOffset(fileContent, [0x10, 0x00, 0x10, 0x00, 0x50, 0x4e]);
    if (offset < 0) {
        console.log('Could not find patient name in file');
    } else {
        //console.log('Found patient name at offset:', offset);
        var len1 = dataView.getUint8(offset + 6);
        var len2 = dataView.getUint8(offset + 7);
        lenPatientsName = (len2 * 256) + len1;

        var patientName = '';
        for (var idx = 0; idx < lenPatientsName; idx++) {
            patientName += String.fromCharCode(dataView.getUint8(offset + 8 + idx));
        }

        //console.log('Name length: ', lenPatientsName, 'Name:', patientName);

        // Verify that the patient name is the same found by the dicomparser js library
        if (patientName != dcmFile.PatientsName) {
            console.error('Could not redact the patient name. Found:', patientName,
                ' dicomParser:', dcmFile.PatientsName);
            return;
        }

        for (var i = 0; i < lenPatientsName; i++) {
            dataView.setUint8(offset + 8 + i, 0x58);
        }
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

// Prevent from submit for ajax call. If fields are empty, show error banner. Send data to upload.py.
$('#submit_form').on('click', function(evt) {
     evt.stopPropagation();
     evt.preventDefault();

     $('#bannerjs-emptyfields').addClass('hide');

     if (!$('#experiment').val() || !$('#group_value').val() ){
         $('#bannerjs-emptyfields').removeClass('hide');
         $('#bannerjs-emptyfields').html("Fields in the form should be completed");
     } else if (isFilesToUploadEmpty()) {
         $('#bannerjs-emptyfields').removeClass('hide');
         $('#bannerjs-emptyfields').html("Please select some files to upload");
     } else {
         var data = new FormData();
         data.append('experiment', $('#experiment').val());
         data.append('group_value', $('#group_value').val());

         var form = new FormData();

         // Also pass a map (filename, Id) to the server
         $.each(Object.keys(files_to_upload), function(i, key) {
             data.append('notes_' + key, $('#notes_' + files_to_upload[key].id).val());
             data.append('StudyID_' + key,           files_to_upload[key].StudyID);
             data.append('SeriesNumber_' + key,      files_to_upload[key].SeriesNumber);
             data.append('AcquisitionNumber_' + key, files_to_upload[key].AcquisitionNumber);
             data.append('SeriesInstanceUID_' + key, files_to_upload[key].SeriesInstanceUID);

             $.each(files_to_upload[key], function(j, file) {
                 data.append('filename_' + file.name, file.id);
                 data.append('file_key_' + file.name, key);
                 data.append('files[]', file.content, file.name);
             });
         });

         $.ajax('upload/submit', {
             data: data,
             cache: false,
             contentType: false,
             processData: false,
             type: 'POST'})
             .done( function(data){
                 var response = JSON.parse(data);
                 console.log("Received upload response: ");

                 $.each(response.files, updateFileStatus);
             })
             .fail( function(data){
                 $('#result_error').text('Error: ' + data);
                 $('#result_error').removeClass('hide');
             });
	 }
});

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

    file.id = files_to_upload[file.Key].id;
    files_to_upload[file.Key].push(file);
    //console.log('Files to upload:', files_to_upload[file.Key]);

    var imagesSubmitted = files_to_upload[file.Key].length;

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

    if (imagesSubmitted == file.ImagesInAcquisition) {
        $('#count_' + file.id).html("<b>" + imagesSubmitted + "</b>" + '/' + file.ImagesInAcquisition);
    } else {
        $('#count_' + file.id).html("<b style='color:red;'>" + imagesSubmitted + "</b>" + '/' + file.ImagesInAcquisition);
    }

    files_to_upload[file.Key].totalSize += file.size;
    $('#size_' + file.id).html(humanFileSize(files_to_upload[file.Key].totalSize));
}

function addToIgnoredFilesList(file) {
    if (file.name.substring(0,1) == '.'){
        return;
    }else{
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

function updateFileStatus(idx, fileResult) {
    //console.log('Updating file status for ', fileResult.filename);

    // Hide the 'remove' button since the file has been already processed
    $('#' + fileResult.id + ' td img').remove();

    if (fileResult.status == true) {
        // File was uploaded and processed correctly
        $('#' + fileResult.id).addClass('ok');
        $('#' + fileResult.id + ' td:last').html(fileResult.message);
    } else {
        $('#' + fileResult.id).addClass('error');
        $('#' + fileResult.id + ' td:last').html(fileResult.message);
    }
}

function clearFileList() {
    files_to_upload = {};
    $('#file_list').html('');
    $('#file_list_ignored').html('');
    $('#file_list_header').addClass('hide');
    $('#file_header_ignored').addClass('hide');
    $('#result_error').addClass('hide');
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

    //console.log("handle DND event: " + evt.type);

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
            async.mapSeries(fileList, openFile, function(err, resultList){
                console.log('Done processing files list - Got results: ', resultList.length);
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
    // console.log("Opened file " + file.name);

    var fileReader = new FileReader();
    fileReader.onload = function(evt){
        // console.log('Finished to read content of file:', file.name);

        var fileContent = evt.target.result;
        var filelength = file.name.length;

        try {
            var dcmFile = parseFile(fileContent);
            redactPatientName(fileContent, dcmFile);
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
            file.SlicesPerVolume = dcmFile.SlicesPerVolume;

            file.Key = ['key', file.StudyID, file.SeriesNumber, file.AcquisitionNumber,
                                file.SeriesInstanceUID].join('-');

            var blob = new Blob([fileContent]);
            file.content = blob;

            // Add the file to table of files in the page
            addFileToList(file);
            callback(null, file);

        } catch (err) {
            console.log('Error parsing dicom file:', err);
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
//     console.log('Handle File Input select:', files);

	// Read and parse each selected file
    $.each(files, function(idx, file) {
		processFile(file);
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
