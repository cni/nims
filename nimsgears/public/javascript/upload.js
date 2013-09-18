
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

function redactPatientName(fileContent) {
    var dataView = new DataView(fileContent);
    dataView.setUint8(0, 0xBE);
    dataView.setUint8(1, 0xEF);

    var offset = findOffset(fileContent, [0x10, 0x00, 0x10, 0x00, 0x50, 0x4e]);
    if (offset < 0) {
        console.log('Could not find patient name in file');
    } else {
        console.log('Found patient name at offset:', offset);
        var len1 = dataView.getUint8(offset + 6);
        var len2 = dataView.getUint8(offset + 7);
        var len = (len2 * 256) + len1;
        console.log('Name length: ', len);

        for (var i = 0; i < len; i++) {
            dataView.setUint8(offset + 8 + i, 0x58);
        }
    }
}


var files_to_upload = [];
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

         var filesToRead = files_to_upload.length;
         var form = new FormData();

         // Also pass a map (filename, Id) to the server
         $.each(files_to_upload, function(i, file) {
             data.append('filename_' + file.name, file.id);

             var fileReader = new FileReader();
             fileReader.onload = function(evt){
                 console.log('Finished to load file: ', file.name);

                 var fileContent = evt.target.result;
                 redactPatientName(fileContent);

                 var blob = new Blob([fileContent]);
                 data.append('files[]', blob, file.name );

                 --filesToRead;
                 if( filesToRead == 0 ){
                     console.log("Uploading files: ", files_to_upload.join(', '));

                     $.ajax('upload/submit', {
                         data: data,
                         cache: false,
                         contentType: false,
                         processData: false,
                         type: 'POST'})
                         .done( function(data){
                             var response = JSON.parse(data);
                             console.log("Received upload response: ");
                             console.dir(response);

                             $.each(response.files, updateFileStatus);
                         })
                         .fail( function(data){
                             $('#result_error').text('Error: ' + data);
                             $('#result_error').removeClass('hide');
                         });
                 }
             }

             fileReader.readAsArrayBuffer(file);
         });

     }

});


// Add a file to the bottom list of file in the page
function addFileToList(idx, file) {
    var output = [];
    var id = '_' + (id_generator++);

    // Add our generatered id to the file object
    file.id = id;

    // If there's already a file with same name on the list, override it
    // if ($(file_id)) {
    //     console.log('A file with the same name "', file_id, '"');
    //     $(file_id).remove();
    //
    //     // Delete from DND file list
    //     dnd_files = $.grep(dnd_files, function(dnd_file) {
    //         return dnd_file.name != file.name;
    //     });
    // }
    $('#file_list_header').removeClass('hide');
    output.push('<tr id="', id, '"> \
                    <td><img class="clickable" src="/images/delete.png" title="Remove this file" \
                            onclick="removeFileFromList(\'', id, '\', \'', file.name, '\')" /></td> \
                    <td><strong>', file.name, '</strong></td> \
                    <td>', file.type || 'n/a', '</td> \
                    <td>', file.size, '</td> \
                    <td>', file.lastModifiedDate ? file.lastModifiedDate.toLocaleDateString() : 'n/a', '</td> \
                    <td class="status"></td> \
                </tr>');


    $('#file_list').append(output.join(''));
}

function removeFileFromList(id, fileNameEscaped) {
    var fileName = unescape(fileNameEscaped);
    console.log('Remove file from list: ', fileName);

    $('#' + id).remove();

    // Delete from FileObject list
    files_to_upload = $.grep(files_to_upload, function(item) {
        return item.name != fileName;
    });
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
    $('#file_list_header').addClass('hide');
}

$('#clear_form').on('click', clearFileList);

////////////////////////////////////////////////////////////////
// Drag & Drop functions
////////////////////////////////////////////////////////////////

function handleDnDSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    console.log("handle DND event: " + evt.type);

    // Add each dropped file to the list of selected files
    var files = evt.originalEvent.dataTransfer.files;
    $.each(files, addFileToList);

    // Append to the list of FileObject to upload
    files_to_upload = $.merge(files_to_upload, files);
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

function handleFileInputSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    console.log('Handle File Input select');
//    console.dir(evt);

    var files = evt.target.files;
    $.each(files, addFileToList);

    // Append to the list of FileObject to upload
    files_to_upload = $.merge(files_to_upload, files);
}

$('#files').on('change', handleFileInputSelect);

// Setup the dnd listeners.
$('#drop_zone').on('dragenter', handleDragEnter);
$('#drop_zone').on('dragover', handleDragOver);
$('#drop_zone').on('dragleave', handleDragLeave);
$('#drop_zone').on('drop', handleDnDSelect);

////////////////////////////////////////////////////////////////
// Utils
////////////////////////////////////////////////////////////////


///////////////////////////////////////////////////////////////////////////////////////


// // Progress bar related
// var reader;
// var progress = document.querySelector('.percent');
//
//  function abortRead() {
//    reader.abort();
//  }
//
//  function errorHandler(evt) {
//    switch(evt.target.error.code) {
//      case evt.target.error.NOT_FOUND_ERR:
//        alert('File Not Found!');
//        break;
//      case evt.target.error.NOT_READABLE_ERR:
//        alert('File is not readable');
//        break;
//      case evt.target.error.ABORT_ERR:
//        break; // noop
//      default:
//        alert('An error occurred reading this file.');
//    };
//  }
//
//  function updateProgress(evt) {
//    // evt is an ProgressEvent.
//    if (evt.lengthComputable) {
//      var percentLoaded = Math.round((evt.loaded / evt.total) * 100);
//      // Increase the progress bar length.
//      if (percentLoaded < 100) {
//        progress.style.width = percentLoaded + '%';
//        progress.textContent = percentLoaded + '%';
//      }
//    }
//  }
//
//  function handleFileSelect(evt) {
//    // Reset progress indicator on new file selection.
//    progress.style.width = '0%';
//    progress.textContent = '0%';
//
//    reader = new FileReader();
//    reader.onerror = errorHandler;
//    reader.onprogress = updateProgress;
//    reader.onabort = function(e) {
//      alert('File read cancelled');
//    };
//    reader.onloadstart = function(e) {
//      $('#progress_bar').addClass('loading');
//    };
//    reader.onload = function(e) {
//      // Ensure that the progress bar displays 100% at the end.
//      progress.style.width = '100%';
//      progress.textContent = '100%';
//      //setTimeout("document.getElementById('progress_bar').className='';", 2000);
//    }
//
//
//    // Read in the image file as a binary string.
//    reader.readAsBinaryString(evt.target.files[0]);
//  }
// document.getElementById('files').addEventListener('change', handleFileSelect, false);
