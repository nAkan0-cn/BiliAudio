import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit, parse_qs, urlencode

APP_NAME = 'BiliAudio · B站音频下载'
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def normalize_url(value):
    value = value.strip()
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', value):
        return 'https://www.bilibili.com/video/' + value
    match = re.search(r'https?://[^\s<>"，。]+', value)
    if not match:
        raise ValueError('请粘贴 B站视频链接、分享文字或 BV号。')
    parsed = urlsplit(match.group(0).rstrip(')）'))
    host = (parsed.hostname or '').lower()
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError('链接格式不正确。')
    if host == 'b23.tv':
        return 'https://b23.tv' + parsed.path
    if host not in ('bilibili.com', 'www.bilibili.com', 'm.bilibili.com'):
        raise ValueError('仅支持 bilibili.com 或 b23.tv 的视频链接。')
    if not re.match(r'^/video/(BV[0-9A-Za-z]{10}|av\d+)(?:/|$)', parsed.path):
        raise ValueError('请使用普通投稿视频的链接，例如 bilibili.com/video/BV…')
    page = parse_qs(parsed.query).get('p', ['1'])[0]
    if not page.isdigit() or int(page) < 1:
        raise ValueError('分P编号必须是正整数。')
    return 'https://www.bilibili.com' + parsed.path + ('?' + urlencode({'p': page}) if page != '1' else '')


def ffmpeg_path():
    if getattr(sys, 'frozen', False):
        return str(Path(sys._MEIPASS) / 'ffmpeg.exe')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_mp3(source):
    source = Path(source)
    target = source.with_suffix('.mp3')
    if source == target or target.exists():
        return str(target)
    partial = target.with_name(target.stem + '.converting.mp3')
    try:
        result = subprocess.run([ffmpeg_path(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                                 '-y', '-i', str(source), '-vn', '-codec:a', 'libmp3lame',
                                 '-q:a', '2', str(partial)], capture_output=True,
                                creationflags=CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('MP3 转换失败：' + result.stderr.decode('utf-8', 'replace')[-1200:])
        os.replace(partial, target)
        return str(target)
    finally:
        partial.unlink(missing_ok=True)


def download_worker(settings, events):
    import yt_dlp
    from yt_dlp.postprocessor.common import PostProcessor
    completed = []
    class Logger:
        def debug(self, message):
            pass
        def warning(self, message):
            events.put(('log', '提示：' + message))
        def error(self, message):
            events.put(('log', message))
    class SaveAudio(PostProcessor):
        def run(self, info):
            source = info['filepath']
            if settings['format'] == 'MP3':
                events.put(('status', '正在转换 MP3…'))
                result = convert_mp3(source)
            else:
                result = source
            completed.append(result)
            events.put(('saved', result))
            return [], info
    last_event = [0.0]
    def progress(data):
        if data['status'] == 'downloading':
            now = time.monotonic()
            if now - last_event[0] < 0.2:
                return
            last_event[0] = now
            total = data.get('total_bytes') or data.get('total_bytes_estimate')
            downloaded = data.get('downloaded_bytes', 0)
            speed = data.get('speed') or 0
            events.put(('progress', (downloaded / total * 100 if total else 0,
                                    f'正在下载：{downloaded / 1048576:.1f} MB · {speed / 1048576:.2f} MB/s')))
        elif data['status'] == 'finished':
            events.put(('progress', (100, '下载完成，正在整理文件…')))
    options = {
        'format': 'bestaudio', 'noplaylist': not settings['all_parts'],
        'outtmpl': str(Path(settings['folder']) / '%(title).140B [%(id)s].%(ext)s'),
        'windowsfilenames': True, 'quiet': True, 'no_warnings': False,
        'logger': Logger(), 'progress_hooks': [progress], 'socket_timeout': 20,
        'retries': 3, 'fragment_retries': 3, 'continuedl': True,
        'overwrites': False, 'ignoreerrors': False,
    }
    cookie_temp = tempfile.TemporaryDirectory(prefix='biliaudio-')
    if settings.get('cookies'):
        cookie_copy = str(Path(cookie_temp.name) / 'cookies.txt')
        shutil.copyfile(settings['cookies'], cookie_copy)
        options['cookiefile'] = cookie_copy
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            url = settings['url']
            if urlsplit(url).hostname == 'b23.tv':
                with downloader.urlopen(url) as response:
                    url = normalize_url(response.url)
            if settings['all_parts']:
                url = url.split('?')[0]
            downloader.add_post_processor(SaveAudio(), when='after_move')
            downloader.download([url])
        if not completed:
            raise RuntimeError('没有找到可下载的音频。')
        events.put(('done', len(completed)))
    except Exception as exc:
        events.put(('failed', str(exc)))
    finally:
        cookie_temp.cleanup()


class App:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.events = None
        self.busy = False
        self.cancelling = False
        self.terminal_event = False
        root.title(APP_NAME)
        root.geometry('790x650')
        root.minsize(690, 590)
        root.configure(bg='#f3f6fa')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#f3f6fa')
        style.configure('TLabel', background='#f3f6fa', foreground='#24334a')
        style.configure('TCheckbutton', background='#f3f6fa')
        style.configure('TButton', padding=(12, 8))
        style.configure('Accent.TButton', background='#137d9d', foreground='white')
        style.map('Accent.TButton', background=[('active', '#106c87'), ('disabled', '#9ba7b1')])
        style.configure('Horizontal.TProgressbar', background='#137d9d', troughcolor='#dfe7ef')
        body = ttk.Frame(root, padding=28)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='BiliAudio', font=('Segoe UI', 25, 'bold')).pack(anchor='w')
        ttk.Label(body, text='把视频里的声音，保存到电脑。', font=('Microsoft YaHei UI', 12)).pack(anchor='w', pady=(2, 22))
        self.url = tk.StringVar()
        self.folder = tk.StringVar(value=str(Path.home() / 'Music' / 'BiliAudio'))
        self.fmt = tk.StringVar(value='原始音频')
        self.all_parts = tk.BooleanVar(value=False)
        self.cookies = tk.StringVar()
        ttk.Label(body, text='视频链接 / BV号').pack(anchor='w')
        self.url_entry = ttk.Entry(body, textvariable=self.url, font=('Segoe UI', 11))
        self.url_entry.pack(fill='x', pady=(6, 14), ipady=6)
        ttk.Label(body, text='保存位置').pack(anchor='w')
        line = ttk.Frame(body)
        line.pack(fill='x', pady=(6, 14))
        self.folder_entry = ttk.Entry(line, textvariable=self.folder)
        self.folder_entry.pack(side='left', fill='x', expand=True, ipady=6)
        self.browse = ttk.Button(line, text='选择文件夹', command=self.pick_folder)
        self.browse.pack(side='right', padx=(8, 0))
        line = ttk.Frame(body)
        line.pack(fill='x', pady=(0, 8))
        ttk.Label(line, text='音频格式').pack(side='left')
        self.format_box = ttk.Combobox(line, textvariable=self.fmt, values=['原始音频', 'MP3'], state='readonly', width=13)
        self.format_box.pack(side='left', padx=10)
        self.parts_check = ttk.Checkbutton(line, text='下载全部分P', variable=self.all_parts)
        self.parts_check.pack(side='left', padx=10)
        ttk.Label(body, text='原始音频不再次压缩；MP3 模式同时保留原始音频。', foreground='#64748b').pack(anchor='w', pady=(0, 10))
        line = ttk.Frame(body)
        line.pack(fill='x')
        self.cookie_button = ttk.Button(line, text='导入 Cookies（可选）', command=self.pick_cookies)
        self.cookie_button.pack(side='left')
        self.cookie_clear = ttk.Button(line, text='清除', command=lambda: self.set_cookie(''))
        self.cookie_clear.pack(side='left', padx=5)
        self.cookie_label = ttk.Label(line, text='未导入 · 公开内容通常无需登录', foreground='#64748b')
        self.cookie_label.pack(side='left', padx=4)
        line = ttk.Frame(body)
        line.pack(fill='x', pady=(18, 12))
        self.start_button = ttk.Button(line, text='开始下载', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.cancel_button = ttk.Button(line, text='取消', state='disabled', command=self.cancel)
        self.cancel_button.pack(side='left', padx=8)
        ttk.Button(line, text='打开保存文件夹', command=self.open_folder).pack(side='right')
        self.status = tk.StringVar(value='准备就绪')
        ttk.Label(body, textvariable=self.status, wraplength=680).pack(anchor='w')
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.pack(fill='x', pady=(8, 10))
        self.log = tk.Text(body, height=6, font=('Microsoft YaHei UI', 9), bg='white', fg='#334155', relief='flat', padx=10, pady=8, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)
        ttk.Label(body, text='仅下载你有权保存的内容。支持普通投稿视频与 b23.tv 分享链接。', foreground='#64748b', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.url_entry.focus_set()

    def append(self, value):
        self.log.configure(state='normal')
        self.log.insert('end', value + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def pick_folder(self):
        value = filedialog.askdirectory()
        if value:
            self.folder.set(value)

    def set_cookie(self, value):
        self.cookies.set(value)
        self.cookie_label.configure(text=Path(value).name if value else '未导入 · 公开内容通常无需登录')

    def pick_cookies(self):
        value = filedialog.askopenfilename(title='选择 Netscape 格式 cookies.txt', filetypes=[('Cookies 文本', '*.txt'), ('全部文件', '*.*')])
        if value:
            self.set_cookie(value)

    def open_folder(self):
        try:
            path = Path(self.folder.get()).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror('无法打开文件夹', str(exc))

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.start_button, self.url_entry, self.folder_entry, self.browse,
                       self.parts_check, self.cookie_button, self.cookie_clear]:
            widget.configure(state='disabled' if busy else 'normal')
        self.format_box.configure(state='disabled' if busy else 'readonly')
        self.cancel_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        try:
            url = normalize_url(self.url.get())
            if not self.folder.get().strip():
                raise ValueError('请选择保存文件夹。')
            folder = Path(self.folder.get()).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=folder):
                pass
            if self.cookies.get() and not Path(self.cookies.get()).is_file():
                raise ValueError('Cookies 文件不存在，请重新导入。')
        except Exception as exc:
            messagebox.showerror('请检查输入', str(exc))
            return
        self.folder.set(str(folder))
        self.events = mp.Queue()
        self.terminal_event = False
        self.cancelling = False
        self.progress['value'] = 0
        self.set_busy(True)
        self.status.set('正在解析视频，请稍候…')
        self.append('开始：' + url)
        settings = dict(url=url, folder=str(folder), format=self.fmt.get(),
                        all_parts=self.all_parts.get(), cookies=self.cookies.get())
        self.process = mp.Process(target=download_worker, args=(settings, self.events), daemon=True)
        try:
            self.process.start()
        except Exception as exc:
            self.append('启动失败：' + str(exc))
            self.set_busy(False)
            self.process = None

    def cancel(self):
        if self.process and self.process.is_alive() and not self.cancelling:
            self.cancelling = True
            self.status.set('正在取消…')
            self.cancel_button.configure(state='disabled')
            pid = self.process.pid
            threading.Thread(target=lambda: subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                             capture_output=True, creationflags=CREATE_NO_WINDOW), daemon=True).start()

    def poll(self):
        if self.events:
            try:
                while True:
                    kind, value = self.events.get_nowait()
                    if kind == 'log':
                        self.append(value)
                    elif kind == 'saved':
                        self.append('已保存：' + value)
                    elif kind == 'status':
                        self.status.set(value)
                    elif kind == 'progress':
                        self.progress['value'], status = value
                        self.status.set(status)
                    elif kind == 'done':
                        self.terminal_event = True
                        self.progress['value'] = 100
                        self.status.set(f'完成！已保存 {value} 个音频文件。')
                    elif kind == 'failed':
                        self.terminal_event = True
                        self.status.set('下载失败，详情见下方。')
                        self.append(value + '\n可检查链接和网络；若提示登录，可导入自己的 cookies.txt。')
            except queue.Empty:
                pass
        if self.process and not self.process.is_alive():
            self.process.join()
            self.process = None
            if self.cancelling:
                self.status.set('已取消。重新开始可续传尚未完成的下载。')
            elif not self.terminal_event:
                self.status.set('下载进程意外退出，请重试。')
            self.set_busy(False)
        self.root.after(150, self.poll)

    def close(self):
        if self.busy:
            if not messagebox.askyesno('退出', '正在下载，取消任务并退出？'):
                return
            if self.process and self.process.is_alive():
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
        self.root.destroy()


def main():
    mp.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        run_self_test(sys.argv[2])
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


def run_self_test(report_file):
    import functools
    import http.server
    report = Path(report_file).resolve()
    folder = report.parent / 'self-test-audio'
    folder.mkdir(parents=True, exist_ok=True)
    result = {'ok': False, 'events': []}
    worker = None
    server = None
    try:
        subprocess.run([ffmpeg_path(), '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=1', '-c:a', 'aac', str(folder / 'sample.m4a')],
                       capture_output=True, check=True, creationflags=CREATE_NO_WINDOW)
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(folder)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        events = mp.Queue()
        worker = mp.Process(target=download_worker, args=(dict(
            url=f'http://127.0.0.1:{server.server_port}/sample.m4a', folder=str(folder / 'result'),
            format='MP3', all_parts=False), events))
        worker.start()
        while True:
            event = events.get(timeout=45)
            result['events'].append(event)
            if event[0] in ('done', 'failed'):
                result['ok'] = event[0] == 'done'
                break
        worker.join(5)
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        if worker and worker.is_alive():
            worker.terminate()
        if server:
            server.shutdown()
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
