import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.file_utils import find_ffmpeg_binary

def test_ffmpeg():
    bin_path = find_ffmpeg_binary()
    print(f"FFmpeg binary detected at: {bin_path}")
    assert bin_path is not None, "FFmpeg should be detected on PATH"
    print("FFMPEG TEST PASSED!")

if __name__ == "__main__":
    test_ffmpeg()
