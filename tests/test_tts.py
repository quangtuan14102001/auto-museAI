import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import edge_tts

async def test_tts():
    text = "Xin chào, đây là thử nghiệm âm thanh từ hệ thống Auto Muse AI."
    output_file = "output/test_tts.mp3"
    os.makedirs("output", exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice="vi-VN-HoaiMyNeural")
    await communicate.save(output_file)
    assert os.path.exists(output_file)
    assert os.path.getsize(output_file) > 1000
    print(f"TTS TEST PASSED! File created: {output_file} (Size: {os.path.getsize(output_file)} bytes)")

if __name__ == "__main__":
    asyncio.run(test_tts())
