import sys
import os
import subprocess
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QLabel,
                             QTextEdit, QProgressBar, QFileDialog, QMessageBox,
                             QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QUrl
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
import platform

class WorkerSignals(QObject):
    finished = pyqtSignal()
    output = pyqtSignal(str)
    error = pyqtSignal(str)

class YTDLPWorker(threading.Thread):
    def __init__(self, url, output_dir):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.signals = WorkerSignals()
        self._is_running = True

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            self.signals.output.emit("Downloading video from YouTube...")
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
                "--merge-output-format", "mp4",
                "-o", os.path.join(self.output_dir, "%(title)s.%(ext)s"),
                self.url
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in process.stdout:
                if not self._is_running:
                    process.terminate()
                    return
                self.signals.output.emit(line.strip())
            process.wait()
            video_file = self.find_downloaded_file(self.output_dir, [".mp4"])
            if not video_file:
                self.signals.error.emit("Video file not found")
                return
            self.signals.output.emit("Extracting audio as MP3...")
            mp3_file = video_file.replace(".mp4", ".mp3")
            subprocess.run([
                "ffmpeg", "-i", video_file, "-q:a", "0", "-map", "a", "-y", mp3_file
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.signals.output.emit("Creating 20-second MP3 clip...")
            mp3_clip = mp3_file.replace(".mp3", "_clip.mp3")
            subprocess.run([
                "ffmpeg", "-i", mp3_file, "-t", "20", "-acodec", "libmp3lame", "-y", mp3_clip
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.signals.output.emit("Creating 20-second M4R clip...")
            temp_m4a = mp3_file.replace(".mp3", "_clip.m4a")
            subprocess.run([
                "ffmpeg", "-i", mp3_file, "-t", "20", "-c:a", "aac", "-b:a", "192k", "-vn", "-y", temp_m4a
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            m4r_file = mp3_file.replace(".mp3", ".m4r")
            os.replace(temp_m4a, m4r_file)
            self.signals.output.emit("Download and conversion completed!")
            self.signals.finished.emit()
        except subprocess.CalledProcessError as e:
            self.signals.error.emit(f"Conversion error: {e}")
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")

    def find_downloaded_file(self, directory, extensions):
        for file in os.listdir(directory):
            if any(file.endswith(ext) for ext in extensions):
                return os.path.join(directory, file)
        return None

    def stop(self):
        self._is_running = False

class YTDLPGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.play_file = None
        self.mp3_file = None
        self.m4r_file = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("JesseJesse.com")
        self.setGeometry(100, 100, 500, 600)
        self.setStyleSheet("QMainWindow { background-color: #2b2b2b; } QLabel { color: white; }")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        title = QLabel("PyTones")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)
        url_group = QGroupBox("A Python YT Ringtone Creator")
        url_layout = QVBoxLayout()
        url_input_layout = QHBoxLayout()
        url_input_layout.addWidget(QLabel("Media URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtu.be/...")
        url_input_layout.addWidget(self.url_input)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_url)
        url_input_layout.addWidget(clear_btn)
        url_layout.addLayout(url_input_layout)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Output Directory:"))
        self.dir_input = QLineEdit()
        self.dir_input.setText(os.path.expanduser("~/Downloads/PyTones"))
        dir_layout.addWidget(self.dir_input)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_directory)
        dir_layout.addWidget(browse_btn)
        url_layout.addLayout(dir_layout)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)
        btn_layout = QHBoxLayout()
        self.download_btn = QPushButton("Download")
        self.download_btn.clicked.connect(self.start_download)
        btn_layout.addWidget(self.download_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_download)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(300)
        layout.addWidget(self.video_widget)
        self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.player.setVideoOutput(self.video_widget)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        layout.addWidget(self.output_console)
        playback_layout = QHBoxLayout()
        self.play_button = QPushButton("Play Video")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_video)
        playback_layout.addWidget(self.play_button)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.pause_video)
        playback_layout.addWidget(self.pause_button)
        self.stop_video_button = QPushButton("Stop")
        self.stop_video_button.setEnabled(False)
        self.stop_video_button.clicked.connect(self.stop_video)
        playback_layout.addWidget(self.stop_video_button)
        self.open_mp3_btn = QPushButton("Android Ringtone")
        self.open_mp3_btn.setEnabled(False)
        self.open_mp3_btn.clicked.connect(self.open_mp3)
        playback_layout.addWidget(self.open_mp3_btn)
        self.open_m4r_btn = QPushButton("iPhone Ringtone")
        self.open_m4r_btn.setEnabled(False)
        self.open_m4r_btn.clicked.connect(self.open_m4r)
        playback_layout.addWidget(self.open_m4r_btn)
        layout.addLayout(playback_layout)
        central_widget.setLayout(layout)

    def clear_url(self):
        self.url_input.clear()

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.dir_input.setText(directory)

    def start_download(self):
        url = self.url_input.text().strip()
        output_dir = self.dir_input.text().strip()
        if not url or not output_dir:
            QMessageBox.warning(self, "Warning", "Enter URL and output directory")
            return
        self.output_console.clear()
        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.worker = YTDLPWorker(url, output_dir)
        self.worker.signals.output.connect(self.update_output)
        self.worker.signals.error.connect(self.handle_error)
        self.worker.signals.finished.connect(self.download_finished)
        self.worker.start()

    def stop_download(self):
        if self.worker:
            self.worker.stop()
            self.output_console.append("Stopping download...")
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_bar.setVisible(False)

    def update_output(self, text):
        self.output_console.append(text)

    def handle_error(self, msg):
        self.output_console.append(f"ERROR: {msg}")
        QMessageBox.critical(self, "Error", msg)
        self.download_finished()

    def download_finished(self):
        self.download_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.output_console.append("Download completed.")
        mp4_file = self.worker.find_downloaded_file(self.dir_input.text(), [".mp4"])
        mp3_file = self.worker.find_downloaded_file(self.dir_input.text(), ["_clip.mp3"])
        m4r_file = self.worker.find_downloaded_file(self.dir_input.text(), [".m4r"])
        if mp4_file:
            self.play_file = mp4_file
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.play_file)))
            self.play_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.stop_video_button.setEnabled(True)
        if mp3_file:
            self.mp3_file = mp3_file
            self.open_mp3_btn.setEnabled(True)
        if m4r_file:
            self.m4r_file = m4r_file
            self.open_m4r_btn.setEnabled(True)

    def play_video(self):
        if self.play_file:
            self.player.play()
            self.output_console.append(f"Playing video: {os.path.basename(self.play_file)}")

    def pause_video(self):
        self.player.pause()
        self.output_console.append("Video paused.")

    def stop_video(self):
        self.player.stop()
        self.output_console.append("Video stopped.")

    def open_mp3(self):
        if self.mp3_file:
            self.open_file(self.mp3_file)

    def open_m4r(self):
        if self.m4r_file:
            self.open_file(self.m4r_file)

    def open_file(self, path):
        if platform.system() == "Darwin":
            subprocess.run(["open", "-R", path])
        elif platform.system() == "Windows":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])

    def closeEvent(self, event):
        if self.worker and self.worker.is_alive():
            reply = QMessageBox.question(self, "Confirm Exit",
                                         "Download in progress. Exit anyway?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker.stop()
                self.worker.join()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(43, 43, 43))
    palette.setColor(QPalette.WindowText, Qt.white)
    app.setPalette(palette)
    window = YTDLPGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()


