<?php

function tarsize($path, $recursive)
{
    return 1024 + tardirsize($path . '/', $recursive);
}

function tardirsize($path, $recursive)
{
    $size = (filesize($path) + 1023) >> 9 << 9;
    #echo $path . ': ' . $size . "\n";

    foreach (scandir($path) as $fsitem)
    {
        if ($fsitem != '.' && $fsitem != '..')
        {
            if (!is_dir($path . $fsitem))
            {
                $size += (filesize($path . $fsitem) + 1023) >> 9 << 9;
                #echo $fsitem . ': ' . ((filesize($path . $fsitem) + 1023) >> 9 << 9) . "\n";
            }
            elseif ($recursive)
            {
                $size += tardirsize($path . $fsitem . '/', $recursive);
            }
        }
    }
    return $size;
}

set_time_limit(3600);  # give up after an hour

error_log('POST:::' . $_GET['dirs']);
$cmd = 'tar -cLf - -C ' . getcwd() . ' ' . implode(' ', $_REQUEST['dirs']);
$filename = 'nims_' . time() . '.tar';
#$size = tarsize($path, 1);  # recursive

header('Content-Type: application/x-tar');
header('Content-disposition: attachment; filename="' . $filename . '"');
#header('Content-Length: ' . $size);

$fp = popen($cmd, 'r');
while (!feof($fp))
{
   echo fread($fp, 1048576);
   flush();
}
pclose($fp);

?>
