//Make a JSON out of the form

// $('form').submit(function(){
//     console.log($(this).serializeArray());
//     return false;
// });


$.fn.serializeObject = function()
{
    var o = {};
    var a = this.serializeArray();
    // $.each(a, function(){
 //        if(!o[this.name] !== undefined ){
 //            if( !o[this.name].push ){
 //                o[this.name] = [o[this.name]];
 //            }
 //            o[this.name].push(this.value || '');
 //        }else{
 //            o[this.name] = this.value || '';
 //        }
    });
    return o;
};

$(function(){
    $('form').submit(function(){
        $('#result').text(JSON.stringfy($('form')));
        return false;
    })
});


function addSelectedFiles(files) {
    // files is a FileList of File objects. List some properties.
    var output = [];
    for (var i = 0, f; f = files[i]; i++) {
      output.push('<li><strong>', escape(f.name), '</strong> (', f.type || 'n/a', ') - ',
                  f.size, ' bytes, last modified: ',
                  f.lastModifiedDate ? f.lastModifiedDate.toLocaleDateString() : 'n/a',
                  '</li>');
    }

    $('#file_list').html(output.join(''));
}

function handleFileSelect(evt) {
    console.log("handle file select event: " + evt.type);
    var files = evt.target.files; // FileList object

    // files is a FileList of File objects. List some properties.
    var output = [];
    for (var i = 0, f; f = files[i]; i++) {
      output.push('<li><strong>', escape(f.name), '</strong> (', f.type || 'n/a', ') - ',
                  f.size, ' bytes, last modified: ',
                  f.lastModifiedDate ? f.lastModifiedDate.toLocaleDateString() : 'n/a',
                  '</li>');
    }

    $('#file_list').html(output.join(''));
}

function handleDnDSelect(evt) {
    evt.stopPropagation();
    evt.preventDefault();

    console.log("handle DND event: " + evt.type);

    var files = evt.originalEvent.dataTransfer.files; // FileList object.

    // files is a FileList of File objects. List some properties.
    var output = [];
    for (var i = 0, f; f = files[i]; i++) {
      output.push('<li><strong>', escape(f.name), '</strong> (', f.type || 'n/a', ') - ',
                  f.size, ' bytes, last modified: ',
                  f.lastModifiedDate ? f.lastModifiedDate.toLocaleDateString() : 'n/a',
                  '</li>');
    }

    $('#file_list').append(output.join(''));
}

function handleDragEnter(evt) {
    console.log("drag over event: " + evt.type);
    $("#drop_zone").addClass("over");
}

function handleDragOver(evt) {
    evt.stopPropagation();
    evt.preventDefault();
    evt.originalEvent.dataTransfer.dropEffect = 'copy'; // Explicitly show this is a copy.
}

function handleDragLeave(evt) {
    console.log("drag leave: " + evt.type);
    $("#drop_zone").removeClass("over");
}

$('#files').on('change', handleFileSelect);

// Setup the dnd listeners.
$('#drop_zone').on('dragenter', handleDragEnter);
$('#drop_zone').on('dragover', handleDragOver);
$('#drop_zone').on('dragleave', handleDragLeave);
$('#drop_zone').on('drop', handleDnDSelect);


// Progress bar related
var reader;
 var progress = document.querySelector('.percent');

 function abortRead() {
   reader.abort();
 }

 function errorHandler(evt) {
   switch(evt.target.error.code) {
     case evt.target.error.NOT_FOUND_ERR:
       alert('File Not Found!');
       break;
     case evt.target.error.NOT_READABLE_ERR:
       alert('File is not readable');
       break;
     case evt.target.error.ABORT_ERR:
       break; // noop
     default:
       alert('An error occurred reading this file.');
   };
 }

 function updateProgress(evt) {
   // evt is an ProgressEvent.
   if (evt.lengthComputable) {
     var percentLoaded = Math.round((evt.loaded / evt.total) * 100);
     // Increase the progress bar length.
     if (percentLoaded < 100) {
       progress.style.width = percentLoaded + '%';
       progress.textContent = percentLoaded + '%';
     }
   }
 }

 function handleFileSelect(evt) {
   // Reset progress indicator on new file selection.
   progress.style.width = '0%';
   progress.textContent = '0%';

   reader = new FileReader();
   reader.onerror = errorHandler;
   reader.onprogress = updateProgress;
   reader.onabort = function(e) {
     alert('File read cancelled');
   };
   reader.onloadstart = function(e) {
     $('#progress_bar').addClass('loading');
   };
   reader.onload = function(e) {
     // Ensure that the progress bar displays 100% at the end.
     progress.style.width = '100%';
     progress.textContent = '100%';
     //setTimeout("document.getElementById('progress_bar').className='';", 2000);
   }

   // Read in the image file as a binary string.
   reader.readAsBinaryString(evt.target.files[0]);
 }

