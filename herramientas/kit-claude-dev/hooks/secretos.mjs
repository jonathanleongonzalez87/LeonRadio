// Guarda de secretos.
//
// Bloquea las dos formas en que una clave termina impresa en el chat (y una clave que
// aparece en el chat queda quemada: hay que rotarla):
//  1) leer un archivo que SIEMPRE es secreto (.env, llaves, cookies.txt, rclone.conf…);
//  2) volcar ENTERO un archivo de configuración que mezcla ajustes con claves
//     (settings.json de Claude, db.json, appsettings.json) o todas las variables de entorno.
//     Así se filtraron claves reales en el proyecto de donde sale este kit.
//
// Sigue permitido: pedir UN campo ((Get-Content x.json -Raw | ConvertFrom-Json).campo),
// preguntar si una clave existe (Test-Path, Select-String -Quiet, grep -q) y escribir
// en un .env sin leerlo (Add-Content, >>).

const ARCHIVO_SECRETO =
  /(^|[\\/\s"'=`(])(\.env(\.(local|production|development|test|staging)[\w.-]*)?|\.npmrc|\.pypirc|\.netrc|\.git-credentials|\.pgpass|\.htpasswd|id_[rd]sa|id_ed25519|credentials(\.(json|ya?ml))?|client_secret[\w.-]*|service[-_]account[\w.-]*|token\.json|cookies\.txt|rclone\.conf|kubeconfig)($|[\s"'`\\/,;)])/i;
const EXT_SECRETA = /\.(pem|key|p12|pfx|jks|keystore)(["'\s]|$)/i;
const CARPETA_SECRETA = /[\\/](cookies|secrets?|credenciales|credentials|\.ssh|\.aws)[\\/]/i;
// .env.example y compañía no llevan valores reales.
const PLANTILLA = /\.(example|sample|template|dist)\b/i;

// Config que mezcla ajustes normales con claves: se consulta por campo, nunca completa.
const CONFIG_MIXTA = /\.claude[\\/]settings(\.local)?\.json\b|\bdb\.json\b|\bappsettings(\.[\w-]+)?\.json\b/i;

const IMPRIME =
  /\b(cat|type|more|less|head|tail|nl|od|xxd|strings|bat|gc|Get-Content|Select-String|sls|findstr|grep|e?grep|rg|awk|sed|Write-Host|Write-Output|Out-File|Out-String)\b/i;
const VUELCA_TODO =
  /\b(ConvertTo-Json|Format-List|Format-Table|Out-String|Out-Host)\b|JSON\.stringify|\b(cat|type|head|more|less)\b/i;
const LEE_CRUDO = /\bGet-Content\b|\bgc\b/i;
const SOLO_PREGUNTA = /\bTest-Path\b|-Quiet\b|\bgrep\s+-[a-zA-Z]*q/i;
const VUELCA_ENTORNO =
  /\bprintenv\b|\b(Get-ChildItem|gci|ls|dir)\s+env:|GetEnvironmentVariables\s*\(|(^|[;&|]\s*)(env|set|export\s+-p)\s*($|[|;&>])/i;

function esSecreto(texto) {
  if (PLANTILLA.test(texto)) return false;
  return ARCHIVO_SECRETO.test(texto) || EXT_SECRETA.test(texto) || CARPETA_SECRETA.test(texto);
}

const deny = (motivo) => ({ decision: "deny", motivo });

export function revisar(tool, inp) {
  if (tool === "Bash" || tool === "PowerShell") {
    const cmd = String(inp.command || "");
    if (VUELCA_ENTORNO.test(cmd)) {
      return deny("Bloqueado: volcar las variables de entorno imprime las claves. Consultá solo la que necesites por nombre, o comprobá si existe sin imprimirla.");
    }
    if (esSecreto(cmd) && IMPRIME.test(cmd) && !SOLO_PREGUNTA.test(cmd)) {
      return deny("Bloqueado: ese archivo es secreto (.env / llave / cookies / credenciales) y el comando lo imprimiría en el chat. Para saber si una clave está: Test-Path, Select-String -Quiet o grep -q. Las claves se usan sin verlas.");
    }
    if (CONFIG_MIXTA.test(cmd) && (VUELCA_TODO.test(cmd) || (LEE_CRUDO.test(cmd) && !/ConvertFrom-Json/i.test(cmd)))) {
      return deny("Bloqueado: eso vuelca la configuración ENTERA, que puede incluir claves. Pedí SOLO el campo que necesitás, por ejemplo: (Get-Content archivo.json -Raw | ConvertFrom-Json).campo");
    }
    return null;
  }

  if (tool === "Read" || tool === "Grep" || tool === "Edit") {
    const ruta = String(inp.file_path || inp.path || "");
    if (!ruta) return null;
    if (esSecreto(ruta)) {
      return deny("Bloqueado: ese archivo guarda secretos. No lo abras: las claves se usan sin verlas. Si necesitás los NOMBRES de las variables, leé el .env.example.");
    }
    if (tool === "Read" && CONFIG_MIXTA.test(ruta)) {
      return deny("Bloqueado: ese archivo mezcla ajustes con claves y Read lo imprime entero. Consultá el campo puntual con un comando, por ejemplo: (Get-Content archivo.json -Raw | ConvertFrom-Json).campo");
    }
  }
  return null;
}
