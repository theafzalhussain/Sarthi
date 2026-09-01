# ============================================================
#  SAARTHI — One-Line Installer (Windows)
#
#  User bas ye ek command chalaye PowerShell mein:
#
#    irm https://raw.githubusercontent.com/theafzalhussain/Sarthi/main/install.ps1 | iex
#
#  Ye khud: Python/Git check -> code clone -> dependencies install
#  -> .env banao -> chalu karo. Bas 1 min ka kaam.
# ============================================================

$ErrorActionPreference = "Stop"

function Say($msg, $color = "Cyan") { Write-Host $msg -ForegroundColor $color }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "  [X]  $msg" -ForegroundColor Red; exit 1 }

Say ""
Say "============================================================"
Say "   SAARTHI — Personal AI Agent — Auto Installer"
Say "============================================================"
Say ""

# Kahan install karna hai
$InstallDir = Join-Path $HOME "Sarthi"
$RepoUrl    = "https://github.com/theafzalhussain/Sarthi.git"

# ---- STEP 1: Python check ----
Say "1/5  Python check kar raha hoon..."
try {
    $pyVer = (python --version) 2>&1
    Ok "Python mila: $pyVer"
} catch {
    Die "Python nahi mila. Install karo: https://python.org (install karte waqt 'Add to PATH' tick karo), phir ye command dobara chalao."
}

# ---- STEP 2: Git check ----
Say "2/5  Git check kar raha hoon..."
$hasGit = $false
try {
    $gitVer = (git --version) 2>&1
    Ok "Git mila: $gitVer"
    $hasGit = $true
} catch {
    Warn "Git nahi mila. ZIP download se try karunga."
}

# ---- STEP 3: Code laao (clone ya update) ----
Say "3/5  Code download kar raha hoon -> $InstallDir"
if (Test-Path $InstallDir) {
    Warn "Folder pehle se hai. Update (git pull) kar raha hoon..."
    if ($hasGit -and (Test-Path (Join-Path $InstallDir ".git"))) {
        Push-Location $InstallDir
        git pull
        Pop-Location
    }
    Ok "Code ready hai."
} elseif ($hasGit) {
    git clone $RepoUrl $InstallDir
    Ok "Clone ho gaya."
} else {
    # Git nahi hai -> ZIP download
    $zip = Join-Path $env:TEMP "sarthi.zip"
    Invoke-WebRequest "https://github.com/theafzalhussain/Sarthi/archive/refs/heads/main.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath $env:TEMP -Force
    Move-Item (Join-Path $env:TEMP "Sarthi-main") $InstallDir
    Remove-Item $zip -Force
    Ok "ZIP se download ho gaya."
}

Set-Location $InstallDir

# ---- STEP 4: Dependencies install ----
Say "4/5  Dependencies install kar raha hoon (thoda ruk jao)..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
Ok "Dependencies installed."

# ---- STEP 5: .env banao ----
Say "5/5  Config (.env) set kar raha hoon..."
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Ok ".env ban gaya (.env.example se)."
    Warn "ZAROORI: '.env' file kholo aur apni API key daalo (jaise GROQ_API_KEY=...)."
    Warn "Free key yahan se: https://console.groq.com"
} else {
    Ok ".env pehle se hai — chhoda nahi."
}

Say ""
Say "============================================================"
Ok  "SAARTHI ready hai!  Folder: $InstallDir"
Say "============================================================"
Say ""
Say "Ab chalane ke liye (koi bhi):" "White"
Say "   -> Double-click:  $InstallDir\Sarthi.bat" "White"
Say "   -> Ya command:    python `"$InstallDir\cli.py`"" "White"
Say ""

# Agar .env mein koi key nahi hai to abhi mat chalao (LLM fail hoga)
$envText = Get-Content ".env" -Raw
if ($envText -match "(?m)^\s*(GROQ|GEMINI|NVIDIA|OPENROUTER|BLUESMINDS|OPENCODE|KIRAAI)_API_KEY\s*=\s*\S+") {
    Say "API key mili — abhi chalu kar raha hoon..." "Green"
    python cli.py
} else {
    Warn "Abhi koi API key set nahi hai. Pehle .env mein key daalo, phir Sarthi.bat double-click karo."
}
