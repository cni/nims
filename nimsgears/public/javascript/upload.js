
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
        console.log('Found patient name at offset:', offset);
        var len1 = dataView.getUint8(offset + 6);
        var len2 = dataView.getUint8(offset + 7);
        lenPatientsName = (len2 * 256) + len1;

        var patientName = '';
        for (var idx = 0; idx < lenPatientsName; idx++) {
            patientName += String.fromCharCode(dataView.getUint8(offset + 8 + idx));
        }

        console.log('Name length: ', lenPatientsName, 'Name:', patientName);

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
    console.log('File: ', file);

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
     } else if (files_to_upload.length == 0) {
         $('#bannerjs-emptyfields').removeClass('hide');
         $('#bannerjs-emptyfields').html("Please select some files to upload");
     } else {
         var data = new FormData();
         data.append('experiment', $('#experiment').val());
         data.append('group_value', $('#group_value').val());

         var form = new FormData();

         // Also pass a map (filename, Id) to the server
         console.log('>>>>>>>>>>>>>>>>>>>>', Object.keys(files_to_upload));
         $.each(Object.keys(files_to_upload), function(i, key) {
             if (key.indexOf('key') == 0) {
                 $.each(files_to_upload[key], function(j, file) {
                     data.append('filename_' + file.name, file.id);
                     data.append('files[]', file.content, file.name);
                     console.log("Uploading: ", file.name);
                 });
             }
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

        // Add our generatered id to the file object
        var id = '_' + (id_generator++);
        files_to_upload[file.Key].id = id;

        $('#file_list_header').removeClass('hide');
        var output = [];
        output.push('<tr id="', id, '"> \
                        <td><strong>', file.StudyID , '</strong></td> \
                        <td>', file.SeriesNumber || 'n/a', '</td> \
                        <td>', file.AcquisitionNumber, '</td> \
                        <td>', file.SeriesInstanceUID, '</td> \
                        <td id="count_', id, '">', '</td> \
                        <td class="status">', file.status, '</td> \
                    </tr>');

        $('#file_list').append(output.join(''));
    }

    file.id = files_to_upload[file.Key].id;

    files_to_upload[file.Key].push(file);
    console.log('Files to upload:', files_to_upload[file.Key]);

    $('#count_' + file.id).html(files_to_upload[file.Key].length);

    // files_to_upload = $.merge(files_to_upload, [file]);


}

function addToIgnoredFilesList(file) {
    var output = [];
    $('#file_header_ignored').removeClass('hide');

    output.push('<tr> \
                     <td><strong>', file.name, '</strong></td> \
                     <td>', file.type || "n/a", '</td> \
                     <td>', file.size, '</td> \
                     <td class="status">', file.status, '</td> \
                 </tr>');

    $('#file_list_ignored').append(output.join(''));
}

function updateFileStatus(idx, fileResult) {
    console.log('Updating file status for ', fileResult.filename);

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
    files_to_upload = [];
    $('#file_list').html('');
    $('#file_list_ignored').html('');
    $('#file_list_header').addClass('hide');
    $('#file_header_ignored').addClass('hide');
    $('#result_error').addClass('hide');
}

$('#clear_form').on('click', clearFileList);

////////////////////////////////////////////////////////////////
// Drag & Drop functions
////////////////////////////////////////////////////////////////

function handleDnDSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    console.log("handle DND event: " + evt.type);

    $.each(evt.originalEvent.dataTransfer.items, function(idx, item){
        var entry;
        if (item.getAsEntry) { //Standard HTML5 API
            entry = item.getAsEntry();
        } else if(item.webkitGetAsEntry) { //Webkit implementation of HTML5 API
            entry = item.webkitGetAsEntry();
        }
        console.log("Entry", entry);
        readFileTree(entry, openFileComplete);
    });
}

function openFileComplete(file) {
    console.log("Opened file", file);

    var fileReader = new FileReader();
    fileReader.onload = function(evt){
        console.log('Finished to read content of file:', file.name);

        var fileContent = evt.target.result;
        var filelength = file.name.length;

		try {
            var dcmFile = parseFile(fileContent);
			redactPatientName(fileContent, dcmFile);
			file.status = "Valid File";
            file.StudyID = dcmFile.StudyID;
            file.InstanceNumber = dcmFile.InstanceNumber;
            file.SeriesInstanceUID = dcmFile.SeriesInstanceUID;
            file.AcquisitionNumber = dcmFile.AcquisitionNumber;
            file.SeriesNumber = dcmFile.SeriesNumber;

            file.Key = ['key', file.StudyID, file.SeriesNumber, file.AcquisitionNumber,
                                file.SeriesInstanceUID].join('-');

            var blob = new Blob([fileContent]);
    		file.content = blob;

            files_to_upload[file.key] = file.content;
    		// Add the file to table of files in the page
    	    addFileToList(file);

		} catch (err) {
            console.log('Error parsing dicom file:', err);
			// Could not parse the dicom file
			file.status = "Not valid";

            addToIgnoredFilesList(file);
		}
    }
    fileReader.readAsArrayBuffer(file);
}

//Explore through the file tree
//Traverse recursively through File and Directory entries.
function readFileTree(itemEntry, callback){
    if(itemEntry.isFile){
        readFile(itemEntry, callback);
    }else if(itemEntry.isDirectory){
        var dirReader = itemEntry.createReader();
        dirReader.readEntries(function(entries){
            $.each(entries, function(idx, entry){
                console.log("Found new entry:", entry, " is file: ", entry.isFile);
                readFileTree(entry, callback);
            });
        });
    }
};

//Read FileEntry to get Native File object.
function readFile(fileEntry, callback){
    //Get File object from FileEntry
    fileEntry.file(function(callback, file){
        if(callback){
            callback(file);
        }
    }.bind(this, callback));
};

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

function handleFileInputSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    var files = evt.target.files;
	console.log('Handle File Input select:', files);

	// Read and parse each selected file
    $.each(files, function(idx, file) {
		openFileComplete(file);
    });
}



$('#files').on('change', handleFileInputSelect);

// Setup the dnd listeners.
$('#drop_zone').on('dragenter', handleDragEnter);
$('#drop_zone').on('dragover', handleDragOver);
$('#drop_zone').on('dragleave', handleDragLeave);
$('#drop_zone').on('drop', handleDnDSelect);

