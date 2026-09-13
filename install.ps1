# ============================================================
#  SAARTHI - One-command Windows installer
#
#  PowerShell mein bas ye chalao:
#    irm https://raw.githubusercontent.com/theafzalhussain/Sarthi/main/install.ps1 | iex
#
#  Fresh PC par ye khud:
#    Python -> SAARTHI -> local Ollama AI -> shortcut -> launch
#  install karta hai. User ko API key dene ki zarurat nahi.
# ============================================================

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say($msg, $color = "Cyan") { Write-Host $msg -ForegroundColor $color }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "  [X]  $msg" -ForegroundColor Red; exit 1 }

function Find-Python {
    $candidates = @()
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }

    $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $pythonRoot) {
        $candidates += Get-ChildItem $pythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "\\Scripts\\" } |
            Sort-Object FullName -Descending |
            Select-Object -ExpandProperty FullName
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        try {
            $supported = & $candidate -c "import sys; print('yes' if sys.version_info >= (3, 10) else 'no')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $supported -eq "yes") { return $candidate }
        } catch { }
    }
    return $null
}

function Find-Ollama {
    $candidates = @()
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe")
    $candidates += (Join-Path $env:LOCALAPPDATA "Ollama\ollama.exe")

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Set-EnvValue($Path, $Name, $Value) {
    $parent = Split-Path $Path -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $text = ""
    if (Test-Path $Path) {
        $text = [IO.File]::ReadAllText($Path)
    }
    $pattern = "(?m)^\s*" + [regex]::Escape($Name) + "\s*=[^\r\n]*$"
    $line = "$Name=$Value"
    if ([regex]::IsMatch($text, $pattern)) {
        $text = [regex]::Replace($text, $pattern, $line)
    } else {
        if ($text.Length -gt 0 -and -not $text.EndsWith("`n")) {
            $text += [Environment]::NewLine
        }
        $text += $line + [Environment]::NewLine
    }

    # Windows PowerShell 5.1 ka `-Encoding UTF8` BOM likhta hai. BOM
    # first dotenv key ko tod sakta hai, isliye explicit UTF-8 no-BOM.
    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $text, $utf8NoBom)
}

function Install-ZipSource($Destination) {
    $stage = Join-Path $env:TEMP ("saarthi-install-" + [guid]::NewGuid().ToString("N"))
    $zip = Join-Path $stage "saarthi.zip"
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    try {
        Invoke-WebRequest "https://github.com/theafzalhussain/Sarthi/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive $zip -DestinationPath $stage -Force
        $source = Join-Path $stage "Sarthi-main"

        if (Test-Path $Destination) {
            & robocopy $source $Destination /E /XD .git .venv data /XF .env /NJH /NJS /NDL /NFL /NP | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "Source update failed (robocopy exit $LASTEXITCODE)." }
        } else {
            Move-Item $source $Destination
        }
    } finally {
        if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

function New-SaarthiShortcut($Path, $Launcher, $WorkingDirectory) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $env:ComSpec
    $shortcut.Arguments = "/c `"`"$Launcher`"`""
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = "SAARTHI Personal AI Agent"
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $shortcut.Save()
}

Say ""
Say "============================================================"
Say "   SAARTHI - Personal AI Agent - Auto Installer"
Say "============================================================"
Say ""

$InstallDir = Join-Path $HOME "Sarthi"
$RepoUrl = "https://github.com/theafzalhussain/Sarthi.git"
$GlobalEnv = Join-Path $HOME ".saarthi\.env"

# ---- 1/6: Python 3.10+ ----
Say "1/6  Python check kar raha hoon..."
$Python = Find-Python
if (-not $Python) {
    Warn "Python 3.10+ nahi mila. Python 3.12 install kar raha hoon..."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Die "Python auto-install ke liye winget nahi mila. Python 3.12 install karo: https://python.org/downloads/windows/"
    }
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Die "Python install fail hua (exit $LASTEXITCODE)." }
    $Python = Find-Python
}
if (-not $Python) { Die "Python install hua, lekin python.exe nahi mila. PowerShell dobara khol ke installer chalao." }
$PythonVersion = & $Python --version 2>&1
Ok "$PythonVersion mila."

# ---- 2/6: Source download/update ----
Say "2/6  SAARTHI download/update kar raha hoon -> $InstallDir"
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not (Test-Path $InstallDir)) {
    if ($git) {
        & $git.Source clone --depth 1 $RepoUrl $InstallDir
        if ($LASTEXITCODE -ne 0) { Die "Git clone fail hua (exit $LASTEXITCODE)." }
    } else {
        Install-ZipSource $InstallDir
    }
} elseif ($git -and (Test-Path (Join-Path $InstallDir ".git"))) {
    & $git.Source -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Warn "Git update nahi hua; existing installation use kar raha hoon. Local changes ko pehle save karo."
    }
} else {
    Install-ZipSource $InstallDir
}
Ok "SAARTHI code ready hai."

# ---- 3/6: Isolated Python environment ----
Say "3/6  Private Python environment aur dependencies install kar raha hoon..."
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$recreateVenv = $false
if (Test-Path $VenvDir) {
    if (-not (Test-Path $VenvPython)) {
        $recreateVenv = $true
    } else {
        try {
            $venvSupported = & $VenvPython -c "import sys; print('yes' if sys.version_info >= (3, 10) else 'no')" 2>$null
            if ($LASTEXITCODE -ne 0 -or $venvSupported -ne "yes") {
                $recreateVenv = $true
            }
        } catch {
            $recreateVenv = $true
        }
    }
}
if ($recreateVenv) {
    Warn "Purana/incompatible virtual environment mila; safe tarike se dobara bana raha hoon."
    Remove-Item $VenvDir -Recurse -Force
}
if (-not (Test-Path $VenvPython)) {
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Die "Virtual environment nahi ban saka." }
}
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Die "pip update fail hua." }
& $VenvPython -m pip install --quiet --upgrade --editable $InstallDir
if ($LASTEXITCODE -ne 0) { Die "SAARTHI dependencies install nahi hui." }
Ok "Dependencies isolated .venv mein installed hain."

# Purane installer ne keys $InstallDir\.env mein rakhi thi. Global
# `saarthi` command kisi aur project se chalega, isliye non-empty legacy
# values ko device config mein one-time migrate karo. Existing global
# values jeetti hain; secret values kabhi terminal pe print nahi hoti.
$LegacyEnv = Join-Path $InstallDir ".env"
if (Test-Path $LegacyEnv) {
    $globalValues = @{}
    if (Test-Path $GlobalEnv) {
        foreach ($line in Get-Content $GlobalEnv) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
                $candidate = $matches[2].Trim().Trim('"').Trim("'")
                if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                    $globalValues[$matches[1]] = $true
                }
            }
        }
    }

    $migrated = 0
    foreach ($line in Get-Content $LegacyEnv) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim()
            $plainValue = $value.Trim('"').Trim("'")
            if (-not [string]::IsNullOrWhiteSpace($plainValue) -and -not $globalValues.ContainsKey($name)) {
                Set-EnvValue $GlobalEnv $name $value
                $globalValues[$name] = $true
                $migrated++
            }
        }
    }
    if ($migrated -gt 0) { Ok "$migrated legacy config value(s) device config mein migrate hui." }
}

# ---- 4/6: A backend without asking the user for an API key ----
Say "4/6  AI brain check kar raha hoon..."
$CloudCount = & $VenvPython -c "from saarthi.config import Settings; print(sum(p.name != 'ollama' for p in Settings.load().available_providers))"
if ($LASTEXITCODE -ne 0) { Die "SAARTHI configuration check fail hua." }

if ([int]$CloudCount -eq 0) {
    Say "     API key nahi hai - private local AI (Ollama) setup hoga." "Yellow"
    $Ollama = Find-Ollama
    if (-not $Ollama) {
        Say "     Ollama install kar raha hoon (official ollama.com installer)..." "Yellow"
        $ollamaInstaller = Invoke-RestMethod "https://ollama.com/install.ps1"
        & ([scriptblock]::Create($ollamaInstaller))
        $Ollama = Find-Ollama
    }
    if (-not $Ollama) { Die "Ollama install hua lekin ollama.exe nahi mila. https://ollama.com/download/windows se install karke dobara try karo." }

    $Model = "qwen2.5:3b"
    try {
        $ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
        if ($ram -ge 12GB) { $Model = "qwen2.5:7b" }
    } catch { }

    $ollamaReady = $false
    try {
        Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
        $ollamaReady = $true
    } catch { }
    if (-not $ollamaReady) {
        Start-Process -FilePath $Ollama -ArgumentList "serve" -WindowStyle Hidden
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 500
            try {
                Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
                $ollamaReady = $true
                break
            } catch { }
        }
    }
    if (-not $ollamaReady) { Die "Ollama start nahi hua. Windows restart karke installer dobara chalao." }

    Say "     Local model '$Model' download ho raha hai (one-time, roughly 2-5 GB)..." "Yellow"
    & $Ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "Ollama model '$Model' download fail hua." }

    Set-EnvValue $GlobalEnv "OLLAMA_ENABLED" "true"
    Set-EnvValue $GlobalEnv "OLLAMA_MODEL" $Model
    Ok "Local AI ready hai. Koi API key nahi chahiye."
} else {
    Ok "$CloudCount configured cloud provider(s) mile; Ollama download skip kiya."
}

# Real runtime configuration must now see at least one provider.
$ProviderCount = & $VenvPython -c "from saarthi.config import Settings; print(len(Settings.load().available_providers))"
if ($LASTEXITCODE -ne 0 -or [int]$ProviderCount -lt 1) {
    Die "AI backend setup verify nahi hua; SAARTHI launch nahi karunga."
}

# ---- 5/6: App shortcuts + global project command ----
Say "5/6  Windows shortcuts aur global 'saarthi' command bana raha hoon..."
$Launcher = Join-Path $InstallDir "Sarthi.bat"
$StartMenuDir = [Environment]::GetFolderPath("Programs")
$DesktopDir = [Environment]::GetFolderPath("Desktop")
New-SaarthiShortcut (Join-Path $StartMenuDir "SAARTHI.lnk") $Launcher $InstallDir
New-SaarthiShortcut (Join-Path $DesktopDir "SAARTHI.lnk") $Launcher $InstallDir

# Sirf ek tiny shim PATH mein jaata hai. Pura venv Scripts PATH mein
# daalne se uska python.exe/pip.exe user ke normal tools ko shadow kar
# sakta hai. Shim jaan-boojhkar `cd` nahi karta, isliye VS Code/project
# terminal ka current folder SAARTHI ka working context rehta hai.
$VenvCommand = Join-Path $VenvDir "Scripts\saarthi.exe"
if (-not (Test-Path $VenvCommand)) {
    Die "Global command entry point nahi mila: $VenvCommand"
}
$CommandDir = Join-Path $HOME ".saarthi\bin"
$CommandShim = Join-Path $CommandDir "saarthi.cmd"
New-Item -ItemType Directory -Path $CommandDir -Force | Out-Null
$shimText = "@echo off`r`nif not exist `"$VenvCommand`" (`r`n  echo [ERROR] SAARTHI installation missing. Installer dobara chalao.`r`n  exit /b 1`r`n)`r`n`"$VenvCommand`" %*`r`n"
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($CommandShim, $shimText, $utf8NoBom)

$normalizedCommandDir = $CommandDir.TrimEnd([char]'\')
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathHasCommandDir = $false
foreach ($entry in (($userPath -split ";") | Where-Object { $_ })) {
    if ($entry.TrimEnd([char]'\') -ieq $normalizedCommandDir) {
        $pathHasCommandDir = $true
        break
    }
}
if (-not $pathHasCommandDir) {
    if ([string]::IsNullOrWhiteSpace($userPath)) {
        $userPath = $CommandDir
    } else {
        $userPath = $userPath.TrimEnd(";") + ";" + $CommandDir
    }
    [Environment]::SetEnvironmentVariable("Path", $userPath, "User")
}
if (-not (($env:Path -split ";") | Where-Object { $_.TrimEnd([char]'\') -ieq $normalizedCommandDir })) {
    $env:Path = $env:Path.TrimEnd(";") + ";" + $CommandDir
}
Ok "Desktop/Start Menu shortcuts aur global 'saarthi' command ready hain."

# ---- 6/6: Launch ----
Say "6/6  Final verification complete."
Say ""
Say "============================================================"
Ok "SAARTHI installed aur ready hai!"
Say "   Folder:   $InstallDir" "White"
Say "   App:      Desktop/Start Menu -> SAARTHI" "White"
Say "   Project:  VS Code terminal -> saarthi" "White"
Say "             (existing VS Code ko ek baar restart karo)" "DarkGray"
Say "============================================================"
Say ""
Say "SAARTHI abhi chalu kar raha hoon..." "Green"
Start-Process -FilePath $env:ComSpec -ArgumentList "/c", "`"$Launcher`"" -WorkingDirectory $InstallDir
