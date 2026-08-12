"""
Test Script: Native C# .NET Shell Folder & MTP Device Diagnostic
"""
import os
import subprocess

ps_script = '''
$sh = New-Object -ComObject Shell.Application
$ns = $sh.NameSpace(17)
Write-Host "Namespace 17 Item Count:" $ns.Items().Count
foreach ($item in $ns.Items()) {
    $name = $item.Name
    $path = $item.Path
    $isF = $item.IsFolder
    Write-Host "Item: $name | Path: $path | IsFolder: $isF"
    if ($isF) {
        $folder = $item.GetFolder
        if ($folder -ne $null) {
            $count = $folder.Items().Count
            Write-Host "   -> Folder Items Count: $count"
            foreach ($sub in $folder.Items()) {
                Write-Host "      • Sub: $($sub.Name) (IsFolder: $($sub.IsFolder))"
            }
        }
    }
}
'''

def run_ps():
    res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    print("STDOUT:\n", res.stdout)
    if res.stderr:
        print("STDERR:\n", res.stderr)

if __name__ == "__main__":
    run_ps()
