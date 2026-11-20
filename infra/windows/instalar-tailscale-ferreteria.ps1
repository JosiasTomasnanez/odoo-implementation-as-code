# PC de ferretería → Odoo por Tailscale (docs/runbooks/acceso-remoto.md, «PC de ferretería»).
# Lo ejecuta INSTALAR-TAILSCALE.bat como administrador. Idempotente: se puede correr de nuevo.
#  1. Instala Tailscale (si no está), modo desatendido: queda conectado aunque nadie inicie sesión.
#  2. Se une al tailnet con la clave de un solo uso de tag:ferreteria (solo llega al 443 del servidor).
#  3. Agrega «IP-del-servidor odoo.comercio-ejemplo.example» al hosts (si no está).
#  4. Comprueba que llega a Odoo (443) y que NO llega a otra cosa (22), y abre Odoo.
$ErrorActionPreference = "Stop"
$CLAVE    = "__CLAVE__"                 # tskey-auth-… de un solo uso (la completa el técnico; no va a git)
$SERVIDOR = "100.64.0.1"           # IP de Tailscale del servidor (tailscale ip -4 servidor-ejemplo)
$NOMBRE   = "odoo.comercio-ejemplo.example"
$EQUIPO   = "pc-ferreteria"
$TS       = "$env:ProgramFiles\Tailscale\tailscale.exe"
$HOSTS    = "$env:SystemRoot\System32\drivers\etc\hosts"

function Paso($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Hay que ejecutarlo como administrador (doble clic en INSTALAR-TAILSCALE.bat)." -ForegroundColor Red; exit 1
}

Paso "1. Tailscale"
if (-not (Test-Path $TS)) {
  $msi = "$env:TEMP\tailscale-setup.msi"
  Write-Host "Descargando el instalador oficial..."
  Invoke-WebRequest -UseBasicParsing "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi" -OutFile $msi
  Start-Process msiexec.exe -Wait -ArgumentList "/i `"$msi`" /quiet /norestart TS_UNATTENDEDMODE=always"
  Remove-Item $msi -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 30 -and -not (Test-Path $TS); $i++) { Start-Sleep 2 }
}
if (-not (Test-Path $TS)) { Write-Host "No se pudo instalar Tailscale." -ForegroundColor Red; exit 1 }
Write-Host "Instalado."

Paso "2. Conectar a la red del local (tag:ferreteria)"
$estado = & $TS status 2>$null
if ($LASTEXITCODE -eq 0 -and ($estado -match [regex]::Escape($SERVIDOR))) {
  Write-Host "Ya estaba conectada."
} else {
  if ($CLAVE -like "__*") { Write-Host "Falta la clave de Tailscale en este archivo." -ForegroundColor Red; exit 1 }
  & $TS up --auth-key=$CLAVE --hostname=$EQUIPO --unattended --reset
  if ($LASTEXITCODE -ne 0) { Write-Host "Tailscale no aceptó la clave (¿ya usada o vencida? se genera otra)." -ForegroundColor Red; exit 1 }
}

Paso "3. hosts: $NOMBRE -> $SERVIDOR"
$lineas = Get-Content $HOSTS -ErrorAction SilentlyContinue
$sinNombre = $lineas | Where-Object { $_ -notmatch "\s$([regex]::Escape($NOMBRE))(\s|$)" }
if (($lineas | Where-Object { $_ -match "^\s*$([regex]::Escape($SERVIDOR))\s+$([regex]::Escape($NOMBRE))\s*$" }).Count -eq 0) {
  Copy-Item $HOSTS "$HOSTS.antes-de-tailscale" -Force
  ($sinNombre + "$SERVIDOR`t$NOMBRE   # Odoo por Tailscale (hasta cablear el local)") | Set-Content -Path $HOSTS -Encoding ASCII
  Write-Host "Agregado (copia del anterior: hosts.antes-de-tailscale)."
} else { Write-Host "Ya estaba." }
ipconfig /flushdns | Out-Null

Paso "4. Comprobar"
Start-Sleep 3
$odoo = Test-NetConnection $SERVIDOR -Port 443 -WarningAction SilentlyContinue
$ssh  = Test-NetConnection $SERVIDOR -Port 22  -WarningAction SilentlyContinue
if ($odoo.TcpTestSucceeded) { Write-Host "Odoo (443): llega  OK" -ForegroundColor Green } else { Write-Host "Odoo (443): NO llega (¿servidor apagado?)" -ForegroundColor Yellow }
if (-not $ssh.TcpTestSucceeded) { Write-Host "Otros puertos (22): bloqueados  OK" -ForegroundColor Green } else { Write-Host "OJO: llega al 22; revisar la política de Tailscale" -ForegroundColor Red }

Start-Process "https://$NOMBRE"
Write-Host ""
Write-Host "Listo. Entrá a Odoo y dejá que el navegador guarde la contraseña." -ForegroundColor Green
Write-Host "BORRÁ esta carpeta del pendrive: tiene la clave de Tailscale (ya usada)."
