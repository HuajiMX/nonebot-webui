# NoneBot2 WebUI 一键安装脚本（Windows / PowerShell）
#
# 一行命令安装（需先安装 Python 3.10+）：
#   powershell -ExecutionPolicy Bypass -Command "iex (irm https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.ps1); Install-NoneBotWebUI -Repo HuajiMX/nonebot-webui"
#
# 本机运行（带参数）：
#   .\install.ps1 -Repo owner/repo [-Username admin] [-Password 123456] [-InstallDir 目标目录]

function Install-NoneBotWebUI {
    param(
        [string]$Repo = "",
        [string]$Url = "",
        [string]$Username = "",
        [string]$Password = "",
        [string]$InstallDir = (Join-Path (Get-Location) "nonebot-webui")
    )
    $ErrorActionPreference = "Stop"

    Write-Host "===== NoneBot2 WebUI 一键安装 ====="

    # 1. 检查 Python
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Host "[错误] 未检测到 Python，请先安装 Python 3.10+：https://www.python.org/downloads/"
        exit 1
    }

    # 2. 确定下载地址
    if (-not $Url) {
        if ($Repo) {
            $Url = "https://github.com/$Repo/releases/latest/download/nonebot-webui.zip"
        } else {
            Write-Host "[错误] 请通过 -Repo owner/repo 或 -Url <zip地址> 指定发布源"
            exit 1
        }
    }

    # 3. 下载发布包
    $tmpZip = Join-Path $env:TEMP "nonebot-webui.zip"
    Write-Host "下载发布包：$Url"
    Invoke-WebRequest -Uri $Url -OutFile $tmpZip

    # 4. 解压到安装目录
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Host "解压到：$InstallDir"
    Expand-Archive -Path $tmpZip -DestinationPath $InstallDir -Force
    Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue

    # 5. 运行安装脚本（已内置前端，自动跳过 npm 构建）
    Push-Location $InstallDir
    try {
        $installArgs = @()
        if ($Username) { $installArgs += @("--username", $Username) }
        if ($Password) { $installArgs += @("--password", $Password) }
        python install.py @installArgs
        if ($LASTEXITCODE -ne 0) { throw "安装失败（退出码 $LASTEXITCODE）" }
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "===== 安装完成 ====="
    Write-Host "项目位置：$InstallDir"
    Write-Host "启动方式：进入目录双击 启动WebUI.bat"
    Write-Host "或运行：cd `"$InstallDir`" 然后 .venv\Scripts\python.exe start.py"
}

Install-NoneBotWebUI
