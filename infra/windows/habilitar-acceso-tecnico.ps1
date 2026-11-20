# Acceso remoto del técnico a una PC Windows del local, por SSH y solo por Tailscale.
# Lo ejecuta HABILITAR-ACCESO-TECNICO.bat como administrador. Idempotente: se puede correr de nuevo.
#  1. Instala el servidor OpenSSH de Windows (si no está) y lo deja arrancando solo.
#  2. Acepta solo la llave pública del técnico (sin contraseñas) y abre PowerShell al entrar.
#  3. Firewall: el puerto 22 solo desde la red de Tailscale (100.64.0.0/10).
# Para quitarlo: Configuración → Sistema → Características opcionales → Servidor OpenSSH → Quitar.
$ErrorActionPreference = "Stop"
$LLAVE = "__LLAVE_PUBLICA__"   # ssh-ed25519 … del técnico (la completa el técnico; es pública, pero no va a git)

function Paso($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Hay que ejecutarlo como administrador (doble clic en HABILITAR-ACCESO-TECNICO.bat)." -ForegroundColor Red; exit 1
}
if ($LLAVE -like "__*") { Write-Host "Falta la llave pública del técnico en este archivo." -ForegroundColor Red; exit 1 }

Paso "1. Servidor SSH de Windows"
$cap = Get-WindowsCapability -Online -Name "OpenSSH.Server*" | Select-Object -First 1
if ($cap.State -ne "Installed") {
  Write-Host "Instalando (puede tardar unos minutos)…"
  Add-WindowsCapability -Online -Name $cap.Name | Out-Null
} else { Write-Host "Ya estaba instalado." }
Set-Service sshd -StartupType Automatic
Start-Service sshd

Paso "2. Solo la llave del técnico, sin contraseñas"
$dir = "$env:ProgramData\ssh"
$llaves = Join-Path $dir "administrators_authorized_keys"
Set-Content -Path $llaves -Value $LLAVE -Encoding ascii
icacls $llaves /inheritance:r /grant "*S-1-5-32-544:F" /grant "SYSTEM:F" | Out-Null   # solo Administradores y SYSTEM
$conf = Join-Path $dir "sshd_config"
$texto = Get-Content $conf -Raw
$texto = $texto -replace "(?m)^#?\s*PasswordAuthentication\s+\w+", "PasswordAuthentication no"
if ($texto -notmatch "(?m)^PasswordAuthentication no") { $texto = "PasswordAuthentication no`r`n" + $texto }
Set-Content -Path $conf -Value $texto -Encoding ascii
New-Item -Path "HKLM:\SOFTWARE\OpenSSH" -Force | Out-Null
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null
Restart-Service sshd

Paso "3. Firewall: puerto 22 solo desde Tailscale"
Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue | Disable-NetFirewallRule
$regla = Get-NetFirewallRule -Name "Tecnico-SSH-Tailscale" -ErrorAction SilentlyContinue
if (-not $regla) {
  New-NetFirewallRule -Name "Tecnico-SSH-Tailscale" -DisplayName "SSH del técnico (solo Tailscale)" -Direction Inbound `
    -Protocol TCP -LocalPort 22 -RemoteAddress 100.64.0.0/10 -Action Allow -Profile Any | Out-Null
}

Paso "Listo"
$ip = & "$env:ProgramFiles\Tailscale\tailscale.exe" ip -4 2>$null
Write-Host "Usuario: $env:USERNAME   ·   Equipo: $env:COMPUTERNAME   ·   IP de Tailscale: $ip" -ForegroundColor Green
Write-Host "Pasale estos datos al técnico. El usuario tiene que ser administrador de esta PC."
