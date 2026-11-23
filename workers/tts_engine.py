import os
import asyncio
import requests
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from utils.file_utils import ensure_dir, sanitize_filename
from utils.logger import log_event
from core.media_output import validate_audio_output


class TTSEngineWorker(QThread):
    finished_signal = pyqtSignal(str) # output_path
    error_signal = pyqtSignal(str) # error_message

    def __init__(
        self,
        text: str,
        output_dir: str = "output/audio",
        provider: str = "edge-tts",
        voice: str = "vi-VN-HoaiMyNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        api_key: str = "",
        voice_id: str = ""
    ):
        super().__init__()
        self.text = text
        self.output_dir = ensure_dir(output_dir)
        self.provider = provider
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.api_key = api_key
        self.voice_id = voice_id

    def run(self):
        if not self.text.strip():
            self.error_signal.emit("Nội dung kịch bản audio rỗng!")
            return

        try:
            filename = f"audio_{sanitize_filename(self.text[:20])}_{os.urandom(3).hex()}.mp3"
            out_file = os.path.join(self.output_dir, filename)

            if self.provider == "edge-tts":
                asyncio.run(self._run_edge_tts(out_file))
            elif self.provider == "elevenlabs":
                self._run_elevenlabs(out_file)
            elif self.provider == "fpt":
                self._run_fpt(out_file)
            else:
                raise ValueError(f"Nhà cung cấp TTS không hợp lệ: {self.provider}")

            validate_audio_output(out_file)
            log_event(f"Đã tạo audio TTS thành công: {out_file}", "SUCCESS")
            self.finished_signal.emit(out_file)
        except Exception as e:
            log_event(f"Lỗi khi đọc TTS: {e}", "ERROR")
            self.error_signal.emit(str(e))

    async def _run_edge_tts(self, out_file: str):
        import edge_tts
        clean_text = self.text.strip()
        
        # Chỉ truyền rate nếu khác 0% để tránh Microsoft Edge TTS từ chối kết nối
        rate_arg = self.rate if (self.rate and self.rate not in ["+0%", "0%", "-0%"]) else None

        # Lần thử 1: Thử với voice và rate (nếu có)
        try:
            if rate_arg:
                communicate = edge_tts.Communicate(text=clean_text, voice=self.voice, rate=rate_arg)
            else:
                communicate = edge_tts.Communicate(text=clean_text, voice=self.voice)
            await communicate.save(out_file)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                return
        except Exception:
            pass

        # Lần thử 2: Thử thuần giọng chuẩn không kèm bất kỳ tham số SSML nào
        try:
            communicate = edge_tts.Communicate(text=clean_text, voice=self.voice)
            await communicate.save(out_file)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                return
        except Exception:
            pass

        # Lần thử 3: Fallback đổi giọng nam/nữ nếu giọng chính đang bị nghẽn server MS
        alt_voice = "vi-VN-NamMinhNeural" if "HoaiMy" in self.voice else "vi-VN-HoaiMyNeural"
        communicate = edge_tts.Communicate(text=clean_text, voice=alt_voice)
        await communicate.save(out_file)

    def _run_elevenlabs(self, out_file: str):
        if not self.api_key:
            raise ValueError("Chưa cấu hình ElevenLabs API Key trong Cài đặt!")
        voice = self.voice_id or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        data = {
            "text": self.text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        resp = requests.post(url, json=data, headers=headers, timeout=60)
        if resp.status_code != 200:
            raise Exception(f"ElevenLabs API Error: {resp.status_code} - {resp.text}")
        with open(out_file, "wb") as f:
            f.write(resp.content)

    def _run_fpt(self, out_file: str):
        if not self.api_key:
            raise ValueError("Chưa cấu hình FPT.AI API Key trong Cài đặt!")
        url = "https://api.fpt.ai/hmi/tts/v5"
        headers = {
            "api-key": self.api_key,
            "voice": self.voice or "banmai",
            "speed": "0"
        }
        resp = requests.post(url, data=self.text.encode("utf-8"), headers=headers, timeout=60)
        if resp.status_code != 200:
            raise Exception(f"FPT API Error: {resp.status_code} - {resp.text}")
        data = resp.json()
        audio_url = data.get("async")
        if not audio_url:
            raise Exception("FPT không trả về đường dẫn audio")
        # Download audio from returned async URL
        import time
        for _ in range(30):
            time.sleep(1)
            d_resp = requests.get(audio_url, timeout=20)
            if d_resp.status_code == 200 and len(d_resp.content) > 1000:
                with open(out_file, "wb") as f:
                    f.write(d_resp.content)
                return
        raise Exception("Hết thời gian chờ FPT render audio")
