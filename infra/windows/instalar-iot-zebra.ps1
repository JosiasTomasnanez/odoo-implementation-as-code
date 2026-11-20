# IoT de Odoo + Zebra de etiquetas en una PC Windows del local (ADR 0030, runbook etiquetas-zebra.md).
# Lo ejecuta INSTALAR-IOT-ZEBRA.bat como administrador, o el técnico por SSH:
#   powershell -ExecutionPolicy Bypass -File instalar-iot-zebra.ps1 [-Token '<token de IoT → Conectar>']
# Idempotente: se puede correr de nuevo; lo que ya está, lo deja.
#  1. Impresora «Zebra ZD420 ZPL» (driver genérico de Windows, en crudo) en el puerto USB de la Zebra.
#     Sin driver de Zebra: el IoT manda el ZPL en crudo y la reconoce como de etiquetas por «ZPL» en el nombre.
#  2. IoT de Odoo para Windows (servicio «odoo-iot»), versión fijada y verificada (SHA256 + firma de Odoo S.A.).
#     Busca el instalador junto a este script (descargas\); si no está, lo baja de nightly.odoo.com.
#  3. Con -Token: lo vincula a Odoo (si no, se pega a mano en http://localhost:8069).
#  4. Verifica: el IoT responde y ve la Zebra.
param(
  [string]$Token = "",
  [string]$NombreImpresora = "Zebra ZD420 ZPL",
  [switch]$Reinstalar
)
$ErrorActionPreference = "Stop"

# Versión fijada del IoT. Para actualizarla: bajar el nuevo de
# https://nightly.odoo.com/20.0/nightly/iot/, anotar acá nombre y SHA256, y guardarlo en descargas\.
$IOT_ARCHIVO = "odoo_iot_setup_20.0.20261118.exe"
$IOT_SHA256  = "8CC8BC0BB704824D1810D9B624F67651592AA74F6001E0D36CA92BE290937765"
$IOT_URL     = "https://nightly.odoo.com/20.0/nightly/iot/$IOT_ARCHIVO"

function Paso($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Falla($t) { Write-Host $t -ForegroundColor Red; exit 1 }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Falla "Hay que ejecutarlo como administrador (doble clic en INSTALAR-IOT-ZEBRA.bat)."
}

Paso "1. Impresora $NombreImpresora"
if (Get-Printer -Name $NombreImpresora -ErrorAction SilentlyContinue) {
  Write-Host "Ya estaba."
} else {
  $puerto = Get-PrinterPort | Where-Object { $_.Description -match "Zebra" -and $_.Name -like "USB*" } | Select-Object -First 1
  if (-not $puerto) { Falla "No encuentro la Zebra por USB: enchufarla, prenderla y volver a correr el script." }
  if (-not (Get-PrinterDriver -Name "Generic / Text Only" -ErrorAction SilentlyContinue)) {
    Add-PrinterDriver -Name "Generic / Text Only"
  }
  Add-Printer -Name $NombreImpresora -DriverName "Generic / Text Only" -PortName $puerto.Name
  Write-Host "Creada en el puerto $($puerto.Name)."
}

Paso "2. IoT de Odoo ($IOT_ARCHIVO)"
$servicio = Get-Service -Name "odoo-iot" -ErrorAction SilentlyContinue
if ($servicio -and -not $Reinstalar) {
  Write-Host "Ya estaba instalado (para reinstalar: -Reinstalar)."
} else {
  $local = Join-Path $PSScriptRoot "descargas\$IOT_ARCHIVO"
  if (-not (Test-Path $local)) {
    $dir = Join-Path $env:ProgramData "ejemplo-iot"
    New-Item -ItemType Directory -Force $dir | Out-Null
    $local = Join-Path $dir $IOT_ARCHIVO
    if (-not (Test-Path $local)) {
      Write-Host "Descargando $IOT_URL …"
      $ProgressPreference = "SilentlyContinue"
      Invoke-WebRequest -UseBasicParsing -Uri $IOT_URL -OutFile $local
    }
  }
  $hash = (Get-FileHash $local -Algorithm SHA256).Hash
  if ($hash -ne $IOT_SHA256) { Falla "El instalador no es el esperado (SHA256 $hash). No se instala." }
  $firma = Get-AuthenticodeSignature $local
  if ($firma.Status -ne "Valid" -or $firma.SignerCertificate.Subject -notmatch "O=Odoo S\.A\.") {
    Falla "La firma del instalador no es válida o no es de Odoo S.A. No se instala."
  }
  Write-Host "Instalando (silencioso)…"
  $p = Start-Process $local -ArgumentList "/S" -Wait -PassThru
  if ($p.ExitCode -ne 0) { Falla "El instalador terminó con error $($p.ExitCode)." }
}
Set-Service -Name "odoo-iot" -StartupType Automatic
Start-Service -Name "odoo-iot"

function DatosIot {
  for ($i = 0; $i -lt 12; $i++) {
    try { return (Invoke-WebRequest -UseBasicParsing http://localhost:8069/iot_drivers/data -TimeoutSec 10).Content | ConvertFrom-Json }
    catch { Start-Sleep 5 }
  }
  Falla "El IoT no responde en http://localhost:8069 (ver el servicio odoo-iot)."
}

if ($Token) {
  Paso "3. Vincular con Odoo"
  $cuerpo = @{ jsonrpc = "2.0"; method = "call"; params = @{ token = $Token } } | ConvertTo-Json
  DatosIot | Out-Null
  $r = Invoke-RestMethod -Uri http://localhost:8069/iot_drivers/connect_to_server -Method Post -ContentType "application/json" -Body $cuerpo
  if ($r.result.status -ne "success") { Falla "No se pudo vincular: $($r.result.message)" }
  Write-Host "Vinculado; el IoT se reinicia."
  Start-Sleep 15
}

Paso "4. Verificación"
$d = DatosIot
$impresoras = @($d.devices.printer | ForEach-Object { $_.name })
Write-Host "Servidor: $($d.server_status)"
Write-Host "Impresoras que ve el IoT: $($impresoras -join ', ')"
if ($impresoras -notcontains $NombreImpresora) { Falla "El IoT no ve «$NombreImpresora»." }
if (-not $d.server_status) {
  Write-Host "Falta vincularlo: en Odoo, IoT → Conectar → copiar el token y pegarlo en http://localhost:8069 (o correr con -Token)." -ForegroundColor Yellow
} else {
  Write-Host "Listo. En Odoo: IoT → Configuración → Gestionar impresoras (ver docs/runbooks/etiquetas-zebra.md)." -ForegroundColor Green
}
