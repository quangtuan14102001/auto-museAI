import asyncio
import edge_tts

async def test():
    try:
        c = edge_tts.Communicate("Xin chào các bạn, đây là thử nghiệm giọng nói", "vi-VN-HoaiMyNeural", rate="+0%", pitch="+0Hz")
        await c.save("output/audio/test_debug.mp3")
        print("Success with vi-VN-HoaiMyNeural")
    except Exception as e:
        print("Error with vi-VN-HoaiMyNeural:", e)

    # List available voices
    voices = await edge_tts.list_voices()
    vi_voices = [v["ShortName"] for v in voices if "vi-" in v["ShortName"]]
    print("Available Vietnamese voices:", vi_voices)

if __name__ == "__main__":
    asyncio.run(test())
