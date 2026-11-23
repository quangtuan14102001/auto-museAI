import asyncio
import edge_tts

async def test_variations():
    # Test with rate="+0%" vs no rate
    print("Test 1: with rate and pitch")
    c1 = edge_tts.Communicate("Thử nghiệm 1", "vi-VN-HoaiMyNeural", rate="+0%", pitch="+0Hz")
    await c1.save("output/audio/test1.mp3")
    print("Test 1 passed")

    print("Test 2: with rate only")
    c2 = edge_tts.Communicate("Thử nghiệm 2", "vi-VN-HoaiMyNeural", rate="+10%")
    await c2.save("output/audio/test2.mp3")
    print("Test 2 passed")

if __name__ == "__main__":
    asyncio.run(test_variations())
