$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$ffmpegSource = python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
New-Item -ItemType Directory -Force build-assets | Out-Null
Copy-Item -LiteralPath $ffmpegSource -Destination build-assets\ffmpeg.exe
python -m PyInstaller --noconfirm --clean --onefile --windowed --name BiliAudio-v1.1 --collect-all yt_dlp --exclude-module imageio_ffmpeg --add-binary 'build-assets/ffmpeg.exe;.' app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
