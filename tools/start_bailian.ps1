param(
  [string]$Model = "qwen3.6-max-preview",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

if (-not $env:DASHSCOPE_API_KEY) {
  $secureKey = Read-Host "请输入百炼 DASHSCOPE_API_KEY（不会写入文件）" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
  try {
    $env:DASHSCOPE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    if ($bstr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
  }
}

$env:KEYBOY_LLM_MODEL = $Model
$env:KEYBOY_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

python -m keyboy.app --host $HostName --port $Port

