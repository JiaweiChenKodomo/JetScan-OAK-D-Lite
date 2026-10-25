param([switch]$Validate, [switch]$Web)
$ErrorActionPreference = 'Stop'
$target = 'jw@10.0.0.4'
& ssh -o BatchMode=yes -o ConnectTimeout=10 $target 'true'
if ($LASTEXITCODE -ne 0) { throw 'SSH key access failed. Test ssh jw@10.0.0.4 in this terminal first.' }
$archive = Join-Path $PSScriptRoot 'jetscan-upload.tar.gz'
& tar -czf $archive -C $PSScriptRoot jetscan.py webapp.py web setup.sh validate.sh selftest.py fix-openblas.py check-dependencies.py add-swap.sh finish-setup.sh start-web.sh install-web-user.sh install-web.sh tests README.md HARDWARE.md WEB_GUI.md COMPATIBILITY.md VERIFICATION.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not package scanner files.' }
& scp $archive "${target}:jetscan-upload.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
$remoteDir = 'jetscan-oak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& ssh -t $target "mkdir -p $remoteDir && tar -xzf jetscan-upload.tar.gz -C $remoteDir && cd $remoteDir && chmod u+w web web/vendor tests && bash setup.sh"
if ($LASTEXITCODE -ne 0) { throw "Setup stopped. Read ~/$remoteDir/logs/setup.log on the Nano." }
Write-Host "Installed in ~/$remoteDir."
if ($Validate) {
    & ssh -t $target "cd $remoteDir && bash validate.sh"
    if ($LASTEXITCODE -ne 0) { throw "Hardware validation failed. Read ~/$remoteDir/logs/validation.log." }
}
Write-Host "Validate: ssh -t $target 'cd $remoteDir && bash validate.sh'"
Write-Host "Operate:  ssh -t $target 'cd $remoteDir && bash'"
if ($Web) {
    & ssh $target "cd $remoteDir && bash install-web-user.sh"
    if ($LASTEXITCODE -ne 0) { throw 'Could not configure web startup.' }
    Write-Host 'Open the Nano LAN address on port 8080 in your browser.'
}
