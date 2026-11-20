# Probar y dejar listos los periféricos de un puesto (PC Windows del local).
# Lo ejecuta PROBAR-PERIFERICOS.bat (doble clic). No necesita administrador. Cada paso se puede saltear.
# Guía: docs/runbooks/probar-perifericos-windows.md. Se puede correr las veces que haga falta.
#
#  1. Lista lo que hay enchufado (USB, puertos COM, impresoras) con marca y modelo.
#  2. Balanza Systel: busca la balanza en los puertos COM y muestra el peso en vivo (solo lee).
#  3. Lector de códigos: pide escanear y muestra lo que leyó.
#  4. Impresora de tickets: la deja predeterminada e imprime una página de prueba.
#  5. Acceso directo «Odoo Puesto» en el escritorio: Chrome que imprime sin preguntar.
#  6. Guarda todo en un informe .txt al lado de este archivo (traerlo para docs/relevamiento/hardware.md).
$ErrorActionPreference = "Continue"
$URL_ODOO = "https://odoo.comercio-ejemplo.example/odoo/point-of-sale"
$CARPETA  = Split-Path -Parent $MyInvocation.MyCommand.Path
$INFORME  = Join-Path $CARPETA ("perifericos-{0}-{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format "yyyy-MM-dd-HHmm"))
$lineasInforme = New-Object System.Collections.Generic.List[string]

function Paso($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan; $lineasInforme.Add(""); $lineasInforme.Add("== $t") }
function Anotar($t, $color = "Gray") { Write-Host $t -ForegroundColor $color; $lineasInforme.Add($t) }
function SiNo($pregunta) {
  $r = Read-Host "$pregunta (s/n)"
  return ($r -match "^[sS]")
}

Anotar ("PC: {0}   Windows: {1}   Fecha: {2}" -f $env:COMPUTERNAME,
  (Get-CimInstance Win32_OperatingSystem).Caption, (Get-Date -Format "dd/MM/yyyy HH:mm"))

# ---------------------------------------------------------------- 1
Paso "1. Qué hay enchufado"
$usb = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
  Where-Object { $_.InstanceId -match "^USB\\VID_" -and $_.Class -ne "USB" } |
  Sort-Object FriendlyName -Unique
foreach ($d in $usb) {
  $id = ""
  if ($d.InstanceId -match "VID_([0-9A-F]{4})&PID_([0-9A-F]{4})") { $id = "$($Matches[1]):$($Matches[2])" }
  $estado = "ok"
  if ($d.Status -ne "OK") { $estado = "SIN DRIVER o con error ($($d.Status))" }
  Anotar ("  [{0}] {1}  ({2})  {3}" -f $d.Class, $d.FriendlyName, $id, $estado)
}
$ftdiSinDriver = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
  Where-Object { $_.InstanceId -match "VID_0403" -and $_.Status -ne "OK" }
if ($ftdiSinDriver) {
  Anotar "  OJO: la balanza (cable FTDI) está enchufada pero sin driver." "Yellow"
  Anotar "  Conectá la PC a internet y esperá unos minutos (Windows Update lo instala solo)," "Yellow"
  Anotar "  o bajá el driver «VCP» de https://ftdichip.com/drivers/vcp-drivers/ y volvé a correr esto." "Yellow"
}

# ---------------------------------------------------------------- 2
Paso "2. Balanza Systel (solo lee, no cambia nada)"
function Xor([byte[]]$b) { $r = 0; foreach ($x in $b) { $r = $r -bxor $x }; return [byte]$r }
function Consultar($puerto, [int]$numero, [int]$funcion) {
  # Trama: [número][función][XOR]; la respuesta termina por silencio (protocolo MAX CUORA V7).
  $cuerpo = [byte[]]@($numero, $funcion)
  $pedido = [byte[]]($cuerpo + (Xor $cuerpo))
  $puerto.DiscardInBuffer()
  $puerto.Write($pedido, 0, $pedido.Length)
  $buf = New-Object System.Collections.Generic.List[byte]
  $limite = (Get-Date).AddMilliseconds(300)
  while ((Get-Date) -lt $limite) {
    Start-Sleep -Milliseconds 20
    while ($puerto.BytesToRead -gt 0) { $buf.Add([byte]$puerto.ReadByte()) }
    $todo = $buf.ToArray()
    for ($i = 0; $i -le $todo.Length - 3; $i++) {
      $trama = $todo[$i..($todo.Length - 1)]
      if ($trama[0] -eq $numero -and $trama[1] -eq $funcion -and
          (Xor $trama[0..($trama.Length - 2)]) -eq $trama[-1]) {
        if ($trama.Length -eq 3) { return "" }
        return [Text.Encoding]::ASCII.GetString([byte[]]$trama[2..($trama.Length - 2)])
      }
    }
  }
  return $null
}
function TextoPeso($datos) {
  if ($datos -match "^(-\d{5}|\d{6})([ei])(\d{6})$") {
    $estable = "inestable"; if ($Matches[2] -eq "e") { $estable = "estable" }
    return ("{0:N3} kg ({1}, tara {2:N3} kg)" -f ([int]$Matches[1] / 1000), $estable, ([int]$Matches[3] / 1000))
  }
  return "respuesta: $datos"
}

$puertos = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object -Unique
if (-not $puertos) {
  Anotar "  No hay puertos COM: la balanza no está enchufada, está apagada o le falta el driver (punto 1)." "Yellow"
} else {
  Anotar ("  Puertos COM: {0}" -f ($puertos -join ", "))
  $encontrada = $null
  # Primero 70 (el número de la Cuora probada el 14/10) y 1; después 2 a 99.
  $numeros = @(70, 1) + (2..99 | Where-Object { $_ -ne 70 })
  foreach ($nombre in $puertos) {
    foreach ($velocidad in @(115200, 9600)) {
      Write-Host "  Buscando en $nombre a $velocidad baudios..." -NoNewline
      try {
        $p = New-Object System.IO.Ports.SerialPort $nombre, $velocidad, "None", 8, "One"
        $p.ReadTimeout = 50; $p.Open()
      } catch { Write-Host " no se pudo abrir (¿está abierta en Chrome o en Qendra? cerralos)"; break }
      foreach ($n in $numeros) {
        if ($null -ne (Consultar $p $n 1)) { $encontrada = @{ Puerto = $nombre; Velocidad = $velocidad; Numero = $n }; break }
      }
      if ($encontrada) {
        Write-Host " encontrada" -ForegroundColor Green
        $firma = Consultar $p $encontrada.Numero 2
        Anotar ("  BALANZA: puerto {0}, {1} baudios 8N1, número de balanza {2}" -f $nombre, $velocidad, $encontrada.Numero) "Green"
        if ($firma) { Anotar "  Firma del equipo: $firma" }
        if ($velocidad -ne 115200) { Anotar "  OJO: el módulo del POS usa 115200: anotarlo para ajustarlo." "Yellow" }
        Write-Host "  Peso en vivo 15 segundos: poné y sacá algo de la bandeja..."
        $fin = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $fin) {
          $d = Consultar $p $encontrada.Numero 1
          if ($null -ne $d) { Write-Host ("    " + (TextoPeso $d)) } else { Write-Host "    sin respuesta" }
          Start-Sleep -Milliseconds 700
        }
        Anotar ("  Peso en vivo: ok. En el puesto de Odoo, cargar el número de balanza {0}." -f $encontrada.Numero)
      } else { Write-Host " sin respuesta" }
      $p.Close()
      if ($encontrada) { break }
    }
    if ($encontrada) { break }
  }
  if (-not $encontrada) {
    Anotar "  No respondió ninguna balanza. Revisar: cable USB de la balanza, que esté encendida," "Yellow"
    Anotar "  y anotar el modelo de la placa de datos (Cuora Max / Neo). Con Neo no hay peso en vivo." "Yellow"
  }
}

# ---------------------------------------------------------------- 3
Paso "3. Lector de códigos"
if (SiNo "¿Hay un lector enchufado para probar?") {
  for ($i = 1; $i -le 3; $i++) {
    $leido = Read-Host "  Escaneá un código (prueba $i de 3; Enter vacío para terminar)"
    if (-not $leido) { break }
    Anotar ("  Leyó: {0}  ({1} caracteres)" -f $leido, $leido.Length) "Green"
  }
  Anotar "  Si leyó y pasó solo a la línea siguiente, el lector manda Enter: está bien para Odoo."
  Anotar "  Probar también: un código de un envase curvo, uno chico, y un QR (los lectores láser no leen QR)."
}

# ---------------------------------------------------------------- 4
Paso "4. Impresoras"
$impresoras = @(Get-CimInstance Win32_Printer | Sort-Object Name)
for ($i = 0; $i -lt $impresoras.Count; $i++) {
  $imp = $impresoras[$i]
  $pred = ""; if ($imp.Default) { $pred = "  <- predeterminada" }
  Anotar ("  {0}. {1}  (driver: {2}; puerto: {3}){4}" -f ($i + 1), $imp.Name, $imp.DriverName, $imp.PortName, $pred)
}
$elegida = Read-Host "  Número de la impresora de TICKETS para este puesto (Enter si no hay)"
if ($elegida -match "^\d+$" -and [int]$elegida -ge 1 -and [int]$elegida -le $impresoras.Count) {
  $imp = $impresoras[[int]$elegida - 1]
  # Que Windows no cambie solo la predeterminada (por defecto usa «la última que se usó»).
  Set-ItemProperty "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Windows" -Name LegacyDefaultPrinterMode -Value 1 -Type DWord
  Invoke-CimMethod -InputObject $imp -MethodName SetDefaultPrinter | Out-Null
  Anotar "  Predeterminada: $($imp.Name)" "Green"
  if (SiNo "  ¿Imprimir una página de prueba?") {
    Invoke-CimMethod -InputObject $imp -MethodName PrintTestPage | Out-Null
    Anotar "  Página de prueba enviada. Si sale cortada o muy chica: en las preferencias de la impresora, papel de 80 mm."
  }
} else {
  Anotar "  Sin impresora de tickets en este puesto (la de la balanza no sirve para Odoo)." "Yellow"
}

# ---------------------------------------------------------------- 5
Paso "5. Acceso directo «Odoo Puesto»"
if (-not (SiNo "¿Crear el acceso directo que imprime sin preguntar?")) { Anotar "  Sin acceso directo." } else {
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
            "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) {
  Anotar "  No encontré Chrome ni Edge: instalá Chrome y volvé a correr esto." "Yellow"
} else {
  # --kiosk-printing: imprime el ticket directo en la impresora predeterminada, sin el cuadro de impresión.
  $sh = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Odoo Puesto.lnk"))
  $sh.TargetPath = $chrome
  $sh.Arguments = "--kiosk-printing $URL_ODOO"
  $sh.IconLocation = "$chrome,0"
  $sh.Save()
  Anotar "  Creado en el escritorio: «Odoo Puesto» ($([IO.Path]::GetFileName($chrome)), imprime sin preguntar)." "Green"
  Anotar "  IMPORTANTE: cerrar todas las ventanas del navegador antes de abrirlo; si ya estaba abierto, sigue preguntando."
  if (SiNo "  ¿Que se abra solo al prender la PC?") {
    Copy-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "Odoo Puesto.lnk") ([Environment]::GetFolderPath("Startup")) -Force
    Anotar "  Se abre solo al iniciar sesión."
  }
}
}

# ---------------------------------------------------------------- 6
$lineasInforme | Set-Content -Path $INFORME -Encoding UTF8
Write-Host ""
Write-Host "Listo. Informe guardado en: $INFORME" -ForegroundColor Green
Write-Host "Traelo (o mandale una foto) para anotar el equipo en el relevamiento."
Write-Host "Después, en Odoo: abrí «Odoo Puesto», el puesto, y probá balanza, lector e «Imprimir pedido»."
