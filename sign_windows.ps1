[CmdletBinding(DefaultParameterSetName = 'Verify')]
param(
    [string]$Executable = "$PSScriptRoot\dist\NetworkMapper\NetworkMapper.exe",
    [string]$SignTool,
    [Parameter(Mandatory, ParameterSetName = 'Certificate')]
    [ValidatePattern('^[a-fA-F0-9]{40}$')]
    [string]$Thumbprint,
    [Parameter(ParameterSetName = 'Certificate')]
    [switch]$MachineStore,
    [Parameter(Mandatory, ParameterSetName = 'ArtifactSigning')]
    [string]$ArtifactSigningDll,
    [Parameter(Mandatory, ParameterSetName = 'ArtifactSigning')]
    [string]$Metadata,
    [string]$TimestampUrl = 'https://timestamp.acs.microsoft.com'
)

$ErrorActionPreference = 'Stop'
$exe = Get-Item -LiteralPath $Executable
if ($exe.PSIsContainer -or $exe.Extension -ine '.exe') {
    throw 'Provide the path to the built Windows executable.'
}
$mode = $PSCmdlet.ParameterSetName
if ($mode -eq 'Verify') {
    $existing = Get-AuthenticodeSignature -LiteralPath $exe.FullName
    if ($existing.Status -eq 'NotSigned') {
        throw 'The executable is unsigned. Supply -Thumbprint or -ArtifactSigningDll and -Metadata to sign it.'
    }
}

if (!$SignTool) {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        $SignTool = $command.Source
    } elseif (${env:ProgramFiles(x86)}) {
        $sdkTools = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue
        $candidate = $sdkTools | Sort-Object { [version]$_.Directory.Parent.Name } -Descending |
            Select-Object -First 1
        if ($candidate) {
            $SignTool = $candidate.FullName
        }
    }
}
if (!$SignTool) {
    throw 'SignTool was not found. Install the Windows SDK signing tools or supply -SignTool with its full path.'
}
$tool = (Get-Item -LiteralPath $SignTool).FullName

if ($mode -ne 'Verify') {
    $signOptions = @('sign', '/v', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256',
                     '/d', 'NetworkMapper')
    if ($mode -eq 'ArtifactSigning') {
        $dll = (Get-Item -LiteralPath $ArtifactSigningDll).FullName
        $metadataFile = (Get-Item -LiteralPath $Metadata).FullName
        $signOptions += @('/dlib', $dll, '/dmdf', $metadataFile)
    } else {
        $signOptions += @('/s', 'My', '/sha1', $Thumbprint)
        if ($MachineStore) {
            $signOptions += '/sm'
        }
    }
    & $tool @signOptions $exe.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool signing returned exit code $LASTEXITCODE. Do not package this build."
    }
}

& $tool verify /pa /all /tw /v $exe.FullName
if ($LASTEXITCODE -ne 0) {
    throw "SignTool verification returned exit code $LASTEXITCODE. Do not package this build."
}
$signature = Get-AuthenticodeSignature -LiteralPath $exe.FullName
if ($signature.Status -ne 'Valid' -or !$signature.TimeStamperCertificate) {
    throw 'Windows did not verify a valid, timestamped Authenticode signature.'
}
Write-Output "Verified publisher: $($signature.SignerCertificate.Subject)"
Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256
